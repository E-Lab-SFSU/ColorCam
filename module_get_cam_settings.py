"""
Sim Code to practice getting camera setting values:

Exposure: Digital/Analog Gain
AWB: Red/Blue Gains
Shutterspeed

Things to do:
-Change Metering Mode, view values above. Are they consistent?
-Get a consistent black image, get the above values.

Collect the above data in a CSV file?
Headers: Filename, digital gain, analog gain, red gain, blue gain, shutter speed



"""

import csv
import os
import random
import time

from datetime import datetime
try:
    from picamera import PiCamera
except ImportError:
    PiCamera = None

# Preview Resolution
VID_WIDTH = 640
VID_HEIGHT = 480
VID_RES = (VID_WIDTH, VID_HEIGHT)

# Image Capture Resolution
# Take a Picture, 12MP: 4056x3040
PIC_WIDTH = 4056
PIC_HEIGHT = 3040
PIC_RES = (PIC_WIDTH, PIC_HEIGHT)

# Save CSV Headers
HEADERS = ["file_name", "iso", "analog_gain", "digital_gain", "red_gain", "blue_gain", "shutter_speed (microseconds)"]

# Change this folder for your system
SAVE_CSV_FOLDER = r'/home/pi/Projects/3dprinter_sampling/Test Pictures/7-21-2022'
# SAVE_CSV_FILE gets updated by init_csv_file() (is temporary solution)
SAVE_CSV_FILE = ''

SAVE_IMAGE_FOLDER = r'/home/pi/Projects/3dprinter_sampling/Test Pictures/7-21-2022'


def _normalized_backend_name(camera):
    return str(getattr(camera, "backend_name", "")).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _is_libcamera_camera(camera):
    backend = _normalized_backend_name(camera)
    return (
        backend in ("libcamera", "picamera2", "libcam", "libcamerabackend")
        or "libcamera" in backend
        or backend.startswith("picamera2")
    )


def _get_capture_metadata(camera):
    metadata = getattr(camera, "last_capture_metadata", None)
    if metadata is None:
        getter = getattr(camera, "get_last_capture_metadata", None)
        if callable(getter):
            metadata = getter()
    return metadata if isinstance(metadata, dict) else None


def gen_cam_data(image_file_name, camera, capture_metadata=None):
    if capture_metadata is None:
        capture_metadata = _get_capture_metadata(camera)

    if capture_metadata:
        iso_value = max(1, int(round(float(capture_metadata.get("iso", 0) or 0))))
        analog_gain = float(capture_metadata.get("analog_gain", 0.0) or 0.0)
        digital_gain = float(capture_metadata.get("digital_gain", 1.0) or 1.0)
        red_gain = float(capture_metadata.get("red_gain", 1.0) or 1.0)
        blue_gain = float(capture_metadata.get("blue_gain", 1.0) or 1.0)
        shutter_speed = int(capture_metadata.get("shutter_speed", 0) or 0)
    else:
        analog_gain = float(camera.analog_gain)
        digital_gain = float(camera.digital_gain)

        if _is_libcamera_camera(camera):
            iso_value = max(1, int(round(analog_gain * 100.0)))
        else:
            iso_value = max(1, int(round(float(camera.iso))))

        red_gain, blue_gain = camera.awb_gains
        red_gain = float(red_gain)
        blue_gain = float(blue_gain)
        shutter_speed = int(camera.exposure_speed or 0)

    data_row = [image_file_name, iso_value, analog_gain, digital_gain, red_gain, blue_gain, shutter_speed]
    return data_row


def wait_for_digital_gain_settle(camera, label="digital_gain", max_wait_seconds=6.0, poll_seconds=0.5, epsilon=0.02):
    prev_value = None
    start_time = time.monotonic()

    while time.monotonic() - start_time < max_wait_seconds:
        current_value = float(camera.digital_gain)
        print(f"{label}: {current_value}")
        if prev_value is not None and abs(current_value - prev_value) <= epsilon:
            break
        prev_value = current_value
        time.sleep(poll_seconds)


def get_unique_id():
    current_time = datetime.now()
    unique_id = current_time.strftime("%Y-%m-%d_%H%M%S")
    # print(f"unique_id: {unique_id}")
    return unique_id


def init_csv_file():

    global SAVE_CSV_FILE

    csv_file_name = f"cam_values_{get_unique_id()}.csv"

    SAVE_CSV_FILE = csv_file_name

    full_path = os.path.join(SAVE_CSV_FOLDER, csv_file_name)

    f = open(full_path, 'w', newline="")
    writer = csv.writer(f)
    writer.writerow(HEADERS)
    f.close()


def append_to_csv_file(data_row):

    full_path = os.path.join(SAVE_CSV_FOLDER, SAVE_CSV_FILE)

    # Append to existing CSV File
    f = open(full_path, 'a', newline="")

    writer = csv.writer(f)

    writer.writerow(data_row)

    f.close()
    print(f"File Updated: {full_path}")


def ensure_csv_ready(folder_path):
    global SAVE_CSV_FOLDER, SAVE_CSV_FILE

    folder_path = os.path.normpath(folder_path)
    if (
        os.path.normpath(SAVE_CSV_FOLDER or "") == folder_path
        and SAVE_CSV_FILE
        and os.path.exists(os.path.join(folder_path, SAVE_CSV_FILE))
    ):
        return

    SAVE_CSV_FOLDER = folder_path
    init_csv_file()


def record_capture_metadata(image_path, camera, capture_metadata=None):
    folder_path = os.path.dirname(os.path.abspath(image_path))
    ensure_csv_ready(folder_path)
    data_row = gen_cam_data(image_path, camera, capture_metadata=capture_metadata)
    append_to_csv_file(data_row)
    return data_row


def setup_camera():
    if PiCamera is None:
        raise RuntimeError("picamera is not available on this system.")

    camera = PiCamera()
    # camera.resolution = PIC_RES
    camera.resolution = (VID_WIDTH, VID_HEIGHT)
    camera.framerate = 32
    
    # Set Exposure mode
    # camera.exposure_mode = 'fireworks'
    
    # Set AWB Mode
    # camera.awb_mode = 'tungsten'
    
    wait_for_digital_gain_settle(camera, label="cur_value")
    
    
    return camera



def set_exposure_mode(camera):
    
    # Extract Values
    # camera.resolution = PIC_RES
    
    # Turn Exposure mode back on so camera can adjust to new light
    # camera.exposure_mode = "auto"
    # camera.awb_mode = 'auto'
    
    
    camera.exposure_mode = 'fireworks'
    camera.awb_mode = 'tungsten'
    
    # Set ISO to desired value
    camera.iso = 0
    
    # Wait for Automatic Gain Control to settle.
    wait_for_digital_gain_settle(camera, label="digital_gain")
    
    # Now fix the values
    
    # Exposure Mode
    # camera.framerate = 30
    camera.shutter_speed = 30901
    # camera.shutter_speed = camera.exposure_speed
    camera.exposure_mode = 'off'
    g = camera.awb_gains
    camera.awb_mode = 'off'
    camera.awb_gains = g
    # Must let camera sleep so exposure mode can settle on certain values, else black screen happens
    # time.sleep(settle_time)
    


def get_picture(camera):
    
    image_file_name = f"image_{get_unique_id()}.jpg"
    image_full_path = os.path.join(SAVE_IMAGE_FOLDER, image_file_name)
    
    # datarow = gen_cam_data(image_file_name, camera)
    
    camera.resolution = PIC_RES
    
    # time.sleep(2)
    
    # New way to sleep
    # seconds_to_wait = 2
    # sleep2(seconds_to_wait)
    
    camera.capture(image_full_path)
    #time.sleep(2)
    
    datarow = gen_cam_data(image_file_name, camera)
    
    print(f"Picture Saved: {image_full_path}")
    return datarow
    

def sleep2(seconds_to_wait):
    
    start = time.monotonic()
    elapsed_time = 0
    # for i in range(10):
    while elapsed_time < seconds_to_wait:
        # print(i)
        current_time = time.monotonic()
        elapsed_time = current_time - start
        # print(f"elapsed_time: {elapsed_time}")
    print(f"Waited {elapsed_time} seconds")
    pass


def main():
    # seconds_to_wait = 2
    # sleep2(seconds_to_wait)
    
    init_csv_file()
    # image_file_name = f"image_{get_unique_id()}.jpg"
    
    camera = setup_camera()
    set_exposure_mode(camera)
    
    # gen_cam_data(image_file_name, camera)
    # data_row = get_picture(camera)
    
    # data_row = gen_cam_data(image_file_name, camera)
    
    # print(f"data_row:\n {data_row}")
    # append_to_csv_file(data_row)

    for i in range(100):
        data_row = get_picture(camera)
        append_to_csv_file(data_row)
    
    camera.close()

    pass


if __name__ == "__main__":
    main()
