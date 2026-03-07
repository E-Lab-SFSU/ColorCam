"""
CameraService wraps camera operations behind a backend boundary.

The adapter returned by create_legacy_camera() preserves most of the old
PiCamera-style API so existing GUI code can migrate incrementally.
"""
from __future__ import annotations

import time
from threading import Event, Lock, Thread
from typing import Optional, Tuple

try:
    from picamera import PiCamera
except ImportError:
    PiCamera = None

try:
    from picamera2 import Picamera2, Preview
except ImportError:
    Picamera2 = None
    Preview = None

try:
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
except ImportError:
    H264Encoder = None
    FileOutput = None

try:
    from libcamera import Transform
except ImportError:
    Transform = None

try:
    import cv2
except ImportError:
    cv2 = None


def _as_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class BaseCameraBackend:
    def start_preview(self, window: Tuple[int, int, int, int], alpha: int = 255):
        raise NotImplementedError

    def stop_preview(self):
        raise NotImplementedError

    def is_previewing(self) -> bool:
        raise NotImplementedError

    def set_resolution(self, res: Tuple[int, int]):
        raise NotImplementedError

    def set_rotation(self, rotation: int):
        raise NotImplementedError

    def capture_still(self, path: str, res: Optional[Tuple[int, int]] = None):
        raise NotImplementedError

    def add_overlay(self, buffer, size, window, alpha: int = 255):
        raise NotImplementedError

    def remove_overlay(self, overlay):
        raise NotImplementedError

    def supports_overlay(self) -> bool:
        raise NotImplementedError

    def set_control(self, name: str, value):
        raise NotImplementedError

    def get_control(self, name: str, default=None):
        raise NotImplementedError

    def start_recording(self, path: str):
        raise NotImplementedError

    def wait_recording(self, seconds: float):
        raise NotImplementedError

    def stop_recording(self):
        raise NotImplementedError

    def preferred_video_extension(self) -> str:
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class PicameraBackend(BaseCameraBackend):
    def __init__(self, rotation: int = 0, preview_res: Tuple[int, int] = (960, 720)):
        if PiCamera is None:
            raise RuntimeError("picamera not available on this system.")
        self.camera = PiCamera()
        self.camera.rotation = rotation
        self.camera.resolution = preview_res
        self._overlay = None
        self._previewing = False
        self._recording = False

    def start_preview(self, window: Tuple[int, int, int, int], alpha: int = 255):
        self.camera.start_preview(alpha=alpha, fullscreen=False, window=window)
        self._previewing = True

    def stop_preview(self):
        if self._previewing:
            self.camera.stop_preview()
        self._previewing = False

    def is_previewing(self) -> bool:
        return bool(getattr(self.camera, "preview", None))

    def set_resolution(self, res: Tuple[int, int]):
        self.camera.resolution = res

    def set_rotation(self, rotation: int):
        self.camera.rotation = int(rotation)

    def capture_still(self, path: str, res: Optional[Tuple[int, int]] = None):
        original_res = tuple(self.camera.resolution)
        if res:
            self.camera.resolution = res
        self.camera.capture(path)
        if res:
            self.camera.resolution = original_res

    def add_overlay(self, buffer, size, window, alpha: int = 255):
        if self._overlay:
            self.remove_overlay(self._overlay)
        self._overlay = self.camera.add_overlay(
            buffer,
            size=size,
            fullscreen=False,
            window=window,
            alpha=alpha,
        )
        return self._overlay

    def remove_overlay(self, overlay=None):
        ov = overlay or self._overlay
        if ov:
            self.camera.remove_overlay(ov)
        self._overlay = None

    def supports_overlay(self) -> bool:
        return True

    def set_control(self, name: str, value):
        if name == "resolution":
            self.set_resolution(value)
            return
        if name == "rotation":
            self.set_rotation(value)
            return
        if name == "exposure_speed":
            return
        setattr(self.camera, name, value)

    def get_control(self, name: str, default=None):
        if name == "resolution":
            return tuple(self.camera.resolution)
        if name == "rotation":
            return int(getattr(self.camera, "rotation", 0))
        if name in ("analog_gain", "digital_gain"):
            return _as_float(getattr(self.camera, name, default), default=1.0)
        if name == "exposure_speed":
            return int(getattr(self.camera, "exposure_speed", 0))
        value = getattr(self.camera, name, default)
        if name == "awb_gains" and value is not None:
            return (_as_float(value[0], 1.0), _as_float(value[1], 1.0))
        return value

    def start_recording(self, path: str):
        self.camera.start_recording(path)
        self._recording = True

    def wait_recording(self, seconds: float):
        self.camera.wait_recording(seconds)

    def stop_recording(self):
        if self._recording:
            self.camera.stop_recording()
        self._recording = False

    def preferred_video_extension(self) -> str:
        return ".h264"

    def close(self):
        if self._recording:
            self.stop_recording()
        if self._previewing:
            self.stop_preview()
        self.camera.close()


class LibcameraBackend(BaseCameraBackend):
    """
    Picamera2/libcamera backend.

    Notes:
    - Overlay APIs are not directly compatible with PiCamera overlays.
    - Preview window movement in the legacy GUI may be best-effort depending
      on the preview backend available on the target system.
    """

    def __init__(self, rotation: int = 0, preview_res: Tuple[int, int] = (960, 720)):
        if Picamera2 is None:
            raise RuntimeError("picamera2/libcamera is not available on this system.")

        self.picam2 = Picamera2()
        self._overlay = None
        self._previewing = False
        self._recording = False
        self._encoder = None
        self._preview_window = (0, 0, preview_res[0], preview_res[1])
        self._resolution = tuple(preview_res)
        self._rotation = int(rotation)
        self._started = False

        self._controls = {
            "framerate": 32,
            "iso": 100,
            "contrast": 0,
            "awb_mode": "auto",
            "awb_gains": (1.0, 1.0),
            "exposure_mode": "auto",
            "shutter_speed": 0,
            "led": False,
        }

        self._configure_preview(self._resolution, self._rotation)
        self.picam2.start()
        self._started = True

    def _transform_for_rotation(self, rotation: int):
        if Transform is None:
            return None
        # 180-degree rotation is supported with dual flips.
        if int(rotation) % 360 == 180:
            return Transform(hflip=1, vflip=1)
        return Transform()

    def _reconfigure(self, config):
        was_running = self._started
        if was_running:
            self.picam2.stop()
            self._started = False
        self.picam2.configure(config)
        if was_running:
            self.picam2.start()
            self._started = True

    def _configure_preview(self, res: Tuple[int, int], rotation: int):
        kwargs = {"main": {"size": tuple(res)}}
        transform = self._transform_for_rotation(rotation)
        if transform is not None:
            kwargs["transform"] = transform
        config = self.picam2.create_preview_configuration(**kwargs)
        self._reconfigure(config)

    def start_preview(self, window: Tuple[int, int, int, int], alpha: int = 255):
        x, y, w, h = window
        self._preview_window = window
        if Preview is not None:
            try:
                self.picam2.start_preview(Preview.QTGL, x=x, y=y, width=w, height=h)
            except Exception:
                # Keep running without a dedicated preview window.
                pass
        self._previewing = True

    def stop_preview(self):
        if Preview is not None:
            try:
                self.picam2.stop_preview()
            except Exception:
                pass
        self._previewing = False

    def is_previewing(self) -> bool:
        return self._previewing

    def set_resolution(self, res: Tuple[int, int]):
        self._resolution = tuple(res)
        self._configure_preview(self._resolution, self._rotation)

    def set_rotation(self, rotation: int):
        self._rotation = int(rotation)
        self._configure_preview(self._resolution, self._rotation)

    def capture_still(self, path: str, res: Optional[Tuple[int, int]] = None):
        if res:
            target_res = tuple(res)
            # Temporary still configuration, then restore preview config.
            still_config = self.picam2.create_still_configuration(main={"size": target_res})
            self._reconfigure(still_config)
            self.picam2.capture_file(path)
            self._configure_preview(self._resolution, self._rotation)
            return
        self.picam2.capture_file(path)

    def add_overlay(self, buffer, size, window, alpha: int = 255):
        # PiCamera-style overlays are not supported in this backend yet.
        return None

    def remove_overlay(self, overlay=None):
        self._overlay = None

    def supports_overlay(self) -> bool:
        return False

    def set_control(self, name: str, value):
        if name == "resolution":
            self.set_resolution(tuple(value))
            return
        if name == "rotation":
            self.set_rotation(int(value))
            return

        self._controls[name] = value
        controls = {}
        if name == "exposure_mode":
            controls["AeEnable"] = str(value).lower() != "off"
        elif name == "awb_mode":
            controls["AwbEnable"] = str(value).lower() != "off"
        elif name == "awb_gains":
            red, blue = value
            controls["ColourGains"] = (_as_float(red, 1.0), _as_float(blue, 1.0))
        elif name == "iso":
            controls["AnalogueGain"] = max(1.0, _as_float(value, 100.0) / 100.0)
        elif name == "contrast":
            controls["Contrast"] = _as_float(value, 0.0)
        elif name == "shutter_speed":
            controls["ExposureTime"] = int(value)
            controls["AeEnable"] = False

        if controls:
            try:
                self.picam2.set_controls(controls)
            except Exception:
                pass

    def get_control(self, name: str, default=None):
        if name == "resolution":
            return self._resolution
        if name == "rotation":
            return self._rotation
        if name == "led":
            return False

        metadata = {}
        try:
            metadata = self.picam2.capture_metadata()
        except Exception:
            metadata = {}

        if name == "digital_gain":
            return _as_float(metadata.get("DigitalGain"), 1.0)
        if name == "analog_gain":
            return _as_float(metadata.get("AnalogueGain"), 1.0)
        if name == "exposure_speed":
            return int(metadata.get("ExposureTime", self._controls.get("shutter_speed", 0)))
        if name == "awb_gains":
            gains = metadata.get("ColourGains")
            if isinstance(gains, (list, tuple)) and len(gains) == 2:
                return (_as_float(gains[0], 1.0), _as_float(gains[1], 1.0))
            return self._controls.get("awb_gains", (1.0, 1.0))
        return self._controls.get(name, default)

    def start_recording(self, path: str):
        if H264Encoder is None or FileOutput is None:
            raise RuntimeError("libcamera recording requires picamera2 H264 encoder support.")
        self._encoder = H264Encoder()
        self.picam2.start_recording(self._encoder, FileOutput(path))
        self._recording = True

    def wait_recording(self, seconds: float):
        time.sleep(seconds)

    def stop_recording(self):
        if self._recording:
            try:
                self.picam2.stop_recording()
            except Exception:
                pass
        self._recording = False
        self._encoder = None

    def preferred_video_extension(self) -> str:
        return ".h264"

    def close(self):
        if self._recording:
            self.stop_recording()
        if self._previewing:
            self.stop_preview()
        if self._started:
            self.picam2.stop()
            self._started = False
        self.picam2.close()


class USBCameraBackend(BaseCameraBackend):
    PREVIEW_WINDOW_NAME = "USB Camera Preview"

    def __init__(self, rotation: int = 0, preview_res: Tuple[int, int] = (960, 720), device_index=0):
        if cv2 is None:
            raise RuntimeError("OpenCV (cv2) is not available for USB camera backend.")

        if isinstance(device_index, str) and device_index.isdigit():
            device_index = int(device_index)

        self._device_index = device_index
        self.cap = cv2.VideoCapture(self._device_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Unable to open USB camera device: {self._device_index}")

        self._io_lock = Lock()
        self._preview_window = (0, 0, preview_res[0], preview_res[1])
        self._resolution = tuple(preview_res)
        self._rotation = int(rotation) % 360
        self._last_frame = None

        self._previewing = False
        self._preview_stop = Event()
        self._preview_thread = None

        self._recording = False
        self._record_stop = Event()
        self._record_thread = None
        self._record_writer = None
        self._record_interval = 0.05

        self._controls = {
            "framerate": 20,
            "iso": 100,
            "contrast": 0,
            "awb_mode": "auto",
            "awb_gains": (1.0, 1.0),
            "exposure_mode": "auto",
            "shutter_speed": 0,
            "led": False,
        }

        self.set_resolution(self._resolution)

    def _apply_rotation(self, frame):
        rot = self._rotation % 360
        if rot == 0:
            return frame
        if rot == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        if rot == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        if rot == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        h, w = frame.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), rot, 1.0)
        return cv2.warpAffine(frame, matrix, (w, h))

    def _resize_if_needed(self, frame, target_res):
        target_w, target_h = target_res
        h, w = frame.shape[:2]
        if (w, h) == (target_w, target_h):
            return frame
        return cv2.resize(frame, (target_w, target_h))

    def _read_frame(self):
        with self._io_lock:
            ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        frame = self._apply_rotation(frame)
        return self._resize_if_needed(frame, self._resolution)

    def _preview_loop(self):
        window_enabled = True
        try:
            cv2.namedWindow(self.PREVIEW_WINDOW_NAME, cv2.WINDOW_NORMAL)
        except Exception:
            window_enabled = False

        while not self._preview_stop.is_set():
            frame = self._read_frame()
            if frame is None:
                time.sleep(0.02)
                continue

            self._last_frame = frame
            x, y, w, h = self._preview_window
            preview_frame = self._resize_if_needed(frame, (w, h))

            if window_enabled:
                try:
                    cv2.resizeWindow(self.PREVIEW_WINDOW_NAME, w, h)
                    cv2.moveWindow(self.PREVIEW_WINDOW_NAME, x, y)
                    cv2.imshow(self.PREVIEW_WINDOW_NAME, preview_frame)
                    cv2.waitKey(1)
                except Exception:
                    window_enabled = False

            time.sleep(0.01)

        try:
            cv2.destroyWindow(self.PREVIEW_WINDOW_NAME)
        except Exception:
            pass
        self._previewing = False

    def _record_loop(self):
        while not self._record_stop.is_set():
            frame = None
            if self._previewing and self._last_frame is not None:
                frame = self._last_frame.copy()
            else:
                frame = self._read_frame()

            if frame is None:
                time.sleep(0.02)
                continue

            if self._record_writer is None:
                break

            self._record_writer.write(frame)
            time.sleep(self._record_interval)

        if self._record_writer is not None:
            self._record_writer.release()
            self._record_writer = None
        self._recording = False

    def start_preview(self, window: Tuple[int, int, int, int], alpha: int = 255):
        del alpha
        self._preview_window = tuple(window)
        if self._previewing:
            return
        self._preview_stop.clear()
        self._previewing = True
        self._preview_thread = Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()

    def stop_preview(self):
        if not self._previewing:
            return
        self._preview_stop.set()
        if self._preview_thread is not None:
            self._preview_thread.join(timeout=1.5)
        self._preview_thread = None
        self._previewing = False
        try:
            cv2.destroyWindow(self.PREVIEW_WINDOW_NAME)
        except Exception:
            pass

    def is_previewing(self) -> bool:
        return self._previewing

    def set_resolution(self, res: Tuple[int, int]):
        width, height = int(res[0]), int(res[1])
        self._resolution = (width, height)
        with self._io_lock:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def set_rotation(self, rotation: int):
        self._rotation = int(rotation) % 360

    def capture_still(self, path: str, res: Optional[Tuple[int, int]] = None):
        target_res = tuple(res) if res else self._resolution
        frame = None
        if self._previewing and self._last_frame is not None:
            frame = self._last_frame.copy()
        else:
            frame = self._read_frame()
        if frame is None:
            raise RuntimeError("USB camera could not read a frame for still capture.")
        frame = self._resize_if_needed(frame, target_res)
        ok = cv2.imwrite(path, frame)
        if not ok:
            raise RuntimeError(f"Failed to write captured image to: {path}")

    def add_overlay(self, buffer, size, window, alpha: int = 255):
        del buffer, size, window, alpha
        return None

    def remove_overlay(self, overlay=None):
        del overlay

    def supports_overlay(self) -> bool:
        return False

    def set_control(self, name: str, value):
        if name == "resolution":
            self.set_resolution(tuple(value))
            return
        if name == "rotation":
            self.set_rotation(int(value))
            return
        self._controls[name] = value
        if name == "framerate":
            fps = max(1.0, _as_float(value, 20.0))
            self._record_interval = 1.0 / fps
            with self._io_lock:
                self.cap.set(cv2.CAP_PROP_FPS, fps)

    def get_control(self, name: str, default=None):
        if name == "resolution":
            return self._resolution
        if name == "rotation":
            return self._rotation
        if name in ("digital_gain", "analog_gain"):
            return 1.0
        if name == "exposure_speed":
            return 0
        if name == "awb_gains":
            return self._controls.get("awb_gains", (1.0, 1.0))
        return self._controls.get(name, default)

    def start_recording(self, path: str):
        if self._recording:
            return
        width, height = self._resolution
        fps = max(1.0, _as_float(self._controls.get("framerate", 20), 20.0))
        self._record_interval = 1.0 / fps

        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError(f"Unable to open USB video writer for: {path}")

        self._record_writer = writer
        self._record_stop.clear()
        self._recording = True
        self._record_thread = Thread(target=self._record_loop, daemon=True)
        self._record_thread.start()

    def wait_recording(self, seconds: float):
        time.sleep(seconds)

    def stop_recording(self):
        if not self._recording:
            return
        self._record_stop.set()
        if self._record_thread is not None:
            self._record_thread.join(timeout=2.0)
        self._record_thread = None
        if self._record_writer is not None:
            self._record_writer.release()
            self._record_writer = None
        self._recording = False

    def preferred_video_extension(self) -> str:
        return ".avi"

    def close(self):
        self.stop_recording()
        self.stop_preview()
        with self._io_lock:
            self.cap.release()
        try:
            cv2.destroyWindow(self.PREVIEW_WINDOW_NAME)
        except Exception:
            pass


class CameraService:
    """
    Thread-safe facade for camera operations.
    """

    def __init__(self, backend: Optional[BaseCameraBackend] = None, rotation: int = 0, preview_res=(960, 720)):
        self.backend = backend or PicameraBackend(rotation=rotation, preview_res=preview_res)
        self.lock = Lock()

    def start_preview(self, window: Tuple[int, int, int, int], alpha: int = 255):
        with self.lock:
            self.backend.start_preview(window, alpha)

    def stop_preview(self):
        with self.lock:
            self.backend.stop_preview()

    def is_previewing(self) -> bool:
        with self.lock:
            return self.backend.is_previewing()

    def supports_overlay(self) -> bool:
        with self.lock:
            return self.backend.supports_overlay()

    def set_resolution(self, res: Tuple[int, int]):
        with self.lock:
            self.backend.set_resolution(res)

    def set_rotation(self, rotation: int):
        with self.lock:
            self.backend.set_rotation(rotation)

    def set_control(self, name: str, value):
        with self.lock:
            self.backend.set_control(name, value)

    def get_control(self, name: str, default=None):
        with self.lock:
            return self.backend.get_control(name, default=default)

    def capture_still(self, path: str, res: Optional[Tuple[int, int]] = None):
        with self.lock:
            self.backend.capture_still(path, res=res)

    def add_overlay(self, buffer, size, window, alpha: int = 255):
        with self.lock:
            return self.backend.add_overlay(buffer, size, window, alpha)

    def remove_overlay(self, overlay=None):
        with self.lock:
            self.backend.remove_overlay(overlay)

    def start_recording(self, path: str):
        with self.lock:
            self.backend.start_recording(path)

    def wait_recording(self, seconds: float):
        with self.lock:
            self.backend.wait_recording(seconds)

    def stop_recording(self):
        with self.lock:
            self.backend.stop_recording()

    def preferred_video_extension(self) -> str:
        with self.lock:
            return self.backend.preferred_video_extension()

    def close(self):
        with self.lock:
            self.backend.close()


class LegacyCameraAdapter:
    """
    PiCamera-style adapter used during migration.
    """

    def __init__(self, service: CameraService):
        self._service = service
        self._preview_window = (0, 0, 640, 480)

    @property
    def preview(self):
        return self._service.is_previewing()

    @property
    def supports_overlay(self):
        return self._service.supports_overlay()

    def start_preview(self, alpha=255, fullscreen=False, window=None):
        del fullscreen
        if window is None:
            window = self._preview_window
        self._preview_window = window
        self._service.start_preview(window=window, alpha=alpha)

    def stop_preview(self):
        self._service.stop_preview()

    @property
    def resolution(self):
        return self._service.get_control("resolution", (640, 480))

    @resolution.setter
    def resolution(self, res):
        self._service.set_resolution(tuple(res))

    @property
    def rotation(self):
        return int(self._service.get_control("rotation", 0))

    @rotation.setter
    def rotation(self, value):
        self._service.set_rotation(int(value))

    @property
    def framerate(self):
        return self._service.get_control("framerate", 32)

    @framerate.setter
    def framerate(self, value):
        self._service.set_control("framerate", value)

    @property
    def iso(self):
        return self._service.get_control("iso", 100)

    @iso.setter
    def iso(self, value):
        self._service.set_control("iso", value)

    @property
    def contrast(self):
        return self._service.get_control("contrast", 0)

    @contrast.setter
    def contrast(self, value):
        self._service.set_control("contrast", value)

    @property
    def awb_mode(self):
        return self._service.get_control("awb_mode", "auto")

    @awb_mode.setter
    def awb_mode(self, value):
        self._service.set_control("awb_mode", value)

    @property
    def awb_gains(self):
        gains = self._service.get_control("awb_gains", (1.0, 1.0))
        return (_as_float(gains[0], 1.0), _as_float(gains[1], 1.0))

    @awb_gains.setter
    def awb_gains(self, value):
        self._service.set_control("awb_gains", value)

    @property
    def exposure_mode(self):
        return self._service.get_control("exposure_mode", "auto")

    @exposure_mode.setter
    def exposure_mode(self, value):
        self._service.set_control("exposure_mode", value)

    @property
    def shutter_speed(self):
        return int(self._service.get_control("shutter_speed", 0))

    @shutter_speed.setter
    def shutter_speed(self, value):
        self._service.set_control("shutter_speed", int(value))

    @property
    def exposure_speed(self):
        return int(self._service.get_control("exposure_speed", self.shutter_speed))

    @property
    def digital_gain(self):
        return _as_float(self._service.get_control("digital_gain", 1.0), 1.0)

    @property
    def analog_gain(self):
        return _as_float(self._service.get_control("analog_gain", 1.0), 1.0)

    @property
    def led(self):
        return bool(self._service.get_control("led", False))

    @led.setter
    def led(self, value):
        self._service.set_control("led", bool(value))

    def capture(self, path):
        self._service.capture_still(path)

    def add_overlay(self, buffer, size=None, fullscreen=False, window=None, alpha=255, **kwargs):
        del fullscreen, kwargs
        if size is None:
            raise ValueError("size is required for add_overlay")
        if window is None:
            window = self._preview_window
        return self._service.add_overlay(buffer=buffer, size=size, window=window, alpha=alpha)

    def remove_overlay(self, overlay=None):
        self._service.remove_overlay(overlay)

    def start_recording(self, path):
        self._service.start_recording(path)

    def wait_recording(self, seconds):
        self._service.wait_recording(seconds)

    def stop_recording(self):
        self._service.stop_recording()

    @property
    def preferred_video_extension(self):
        return self._service.preferred_video_extension()

    def close(self):
        self._service.close()


def create_camera_service(
    backend_name: str = "picamera",
    rotation: int = 0,
    preview_res=(960, 720),
    device_index=0,
) -> CameraService:
    name = (backend_name or "picamera").strip().lower()
    if name in ("picamera", "legacy"):
        backend = PicameraBackend(rotation=rotation, preview_res=preview_res)
    elif name in ("libcamera", "picamera2"):
        backend = LibcameraBackend(rotation=rotation, preview_res=preview_res)
    elif name in ("usb", "webcam", "v4l2"):
        backend = USBCameraBackend(rotation=rotation, preview_res=preview_res, device_index=device_index)
    else:
        raise ValueError(f"Unknown camera backend: {backend_name}")
    return CameraService(backend=backend)


def create_legacy_camera(
    backend_name: str = "picamera",
    rotation: int = 0,
    preview_res=(960, 720),
    device_index=0,
) -> LegacyCameraAdapter:
    service = create_camera_service(
        backend_name=backend_name,
        rotation=rotation,
        preview_res=preview_res,
        device_index=device_index,
    )
    return LegacyCameraAdapter(service)
