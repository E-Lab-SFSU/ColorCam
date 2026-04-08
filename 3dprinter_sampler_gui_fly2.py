"""
Graphical User Interface for using the 3D Printer to take picture/video samples
Author: Johnny Duong
Projects: Cell Sensor and MHT
San Francisco State University

Current Features:
-Has Camera Feed
-Can move X, Y, Z of 3D Printer in various relative direction and increments
-Can get Current Location of Extruder Nozzle
-Input Custom GCode

Future Features:
-Smart Movement: Only take a picture or video if current location is
                 the destination (+/- 1 mm)
-Be able to take picture/video without interferring with camera feed
-Save/Open CSV Option for locations
-Preview Sample Locations
-Run Experiment (photo or video, maybe use a radio button)
   -Run for x iterations
-Camera Settings (white balance, sharpness, and so on)
-Display Current Location in GUI

Current TODO List:
-Get Current Location Manager (runs it twice to get location)
-Put GUI Keys/Text as Constants
-Experiment with Tabs
 Source: https://github.com/PySimpleGUI/PySimpleGUI/blob/master/DemoPrograms/Demo_Tabs_Simple.py
         https://csveda.com/creating-tabbed-interface-using-pysimplegui/

Changelog
01 Jan 2025: Replace PySimpleGUI with FreeSimpleGUI
10 Oct 2023: Created easy_rot quick access camera rotation variable
24 Aug 2022: User can choose where to save experiment folder (CAM tab)
16 May 2022: Removed PiRGBArray Camera Preview and implemented PiCamera Preview + hacks for window control!
25 Apr 2022: Fixed restart bug, can now run multiple experiments without restarting GUI!
             Solution: Use flag to make experiment function end and make forever while loop.
21 Apr 2022: Added in Z Stack Creator
13 Apr 2022: Added Camera Tab to adjust picture capture resolution for "Pic" button and will show resize image.
06 Jun 2021: Can take pictures in Experiment Thread. No video yet. Can't change resolution, bugs out. Buffer issue?
05 Jun 2021: Added in Experiment Thread, can now run GUI and Experiment at the same time.
28 Apr 2021: Changed Experiment variables into CONSTANTS
26 Apr 2021: Added in 2 Tabs: Start Experiment and Movement
18 Apr 2021: Started Changelog, Allow user to input their own GCode..

"""

# Import FreeSimpleGUI, cv2, numpy, time libraries
# Import camera backend adapter

from datetime import datetime
from Xlib.display import Display
import csv
import FreeSimpleGUI as sg
import cv2
import numpy as np
import os
import time
import threading
import random

# Import modules
import settings as C
import get_current_location_m114 as GCL
import printer_connection as printer
import prepare_experiment as P
import module_get_cam_settings as GCS
import module_experiment_timer as ET
import module_well_location_helper as WL
import module_well_location_calculator as WLC
from module_snake_path import generate_snake_csv
from camera_service import create_legacy_camera


easy_rot = 180 #global variable for camera rotation, moved for access
# ==== USER CONSTANTS - GUI ====
# TODO: Put these in a YAML GUI Settings File?

# ---- EXPERIMENT CONSTANTS ----
OPEN_CSV_PROMPT = "Open CSV:"
OPEN_CSV_FILEBROWSE_KEY = "-CSV_INPUT-"
START_EXPERIMENT = "Start Experiment"
STOP_EXPERIMENT = "Stop Experiment"
PAUSE_EXPERIMENT = "Pause"
RESUME_EXPERIMENT = "Resume"
MAX_NUMBER_EXPERIMENTAL_RUNS = 1

# ---- RADIO GUI KEYS AND TEXT ----
EXP_RADIO_PIC_KEY = "-RADIO_PIC-"
EXP_RADIO_VID_KEY = "-RADIO_VID-"
EXP_RADIO_PREVIEW_KEY = "-RADIO_PREVIEW-"
EXP_RADIO_GROUP = "RADIO_EXP"
EXP_RADIO_PIC_TEXT = "Picture"
EXP_RADIO_VID_TEXT = "Video"
EXP_RADIO_PREVIEW_TEXT = "Preview"
EXP_RADIO_PROMPT = "Experiment mode"

# ---- CAMERA TAB ----
# CONSTANTS
DEFAULT_SAMPLE_DIR = os.path.join(os.path.expanduser("~"), "Projects", "3dprinter_sampling")
PIC_SAVE_FOLDER = DEFAULT_SAMPLE_DIR

# Video Streaming:
# Old = 640x480
"""
VID_WIDTH = 640
VID_HEIGHT = 480
"""
VID_WIDTH = 960
VID_HEIGHT = 720
VID_RES = (VID_WIDTH, VID_HEIGHT)

# Image Capture Resolution
# Take a Picture, 12MP: 4056x3040
PIC_WIDTH = 1920 #KEEF
PIC_HEIGHT = 1080
PIC_RES = (PIC_WIDTH, PIC_HEIGHT)

# Monitor Resolution (The one you're using to look at this)
MON_WIDTH = 1920
MON_HEIGHT = 1080
MON_RES = (MON_WIDTH, MON_HEIGHT)

# GUI CONSTANTS
# Button Labels:
UPDATE_CAMERA_TEXT = "Update Camera Settings"

# Camera GUI Keys
CAMERA_ROTATION_KEY = "-ROTATION_INPUT-"
PIC_WIDTH_KEY = "-PIC_WIDTH_INPUT-"
PIC_HEIGHT_KEY = "-PIC_HEIGHT_INPUT-"
PIC_SAVE_FOLDER_KEY = "-PIC_SAVE_FOLDER_INPUT-"


# --- MOVEMENT CONSTANTS ----
# Radio Keys
RELATIVE_TENTH_KEY = "-REL_TENTH-"
RELATIVE_ONE_KEY = "-REL_ONE-"
RELATIVE_TEN_KEY = "-REL_TEN-"
RADIO_GROUP = "RADIO1"
RELATIVE_TENTH_TEXT = "0.10mm"
RELATIVE_ONE_TEXT = "1.00mm"
RELATIVE_TEN_TEXT = "10.00mm"
DEFAULT_DISTANCE = "0.00"

# X+, X-, Y+, Y-, Z+, or Z-
X_PLUS = "X+"
X_MINUS = "X-"
Y_PLUS = "Y+"
Y_MINUS = "Y-"
Z_PLUS = "Z+"
Z_MINUS = "Z-"
# WINDOW_GUI_TIMEOUT
WINDOW_GUI_TIMEOUT = 10 # in ms
# TODO: Put in Constants for GCODE Input

# --- Z Stack Constants ----
# INPUT Z STACK PARAMETERS Keys
Z_START_KEY = "-Z_START_KEY-"
Z_END_KEY = "-Z_END_KEY-"
Z_INC_KEY = "-Z_INC_KEY-"

SAVE_FOLDER_KEY = "-SAVE_FOLDER_KEY-"

# Button Text
START_Z_STACK_CREATION_TEXT = "Start Z Stack Creation"


# --- Save a Location Constants ---
SAVE_LOC_BUTTON = "Save Loc Button"

# Create Temp file to store locations into
TEMP_FOLDER = os.path.join(DEFAULT_SAMPLE_DIR, "temp")
TEMP_FILE = r"temp_loc.csv"
TEMP_FULL_PATH = os.path.join(TEMP_FOLDER, TEMP_FILE)

# --- Camera Preview Settings ---
# GUI KEYS
PREVIEW_LOC_X_KEY = "-PREVIEW LOC X KEY-"
PREVIEW_LOC_Y_KEY = "-PREVIEW LOC Y KEY-"
PREVIEW_WIDTH_KEY = "-PREVIEW WIDTH KEY-"
PREVIEW_HEIGHT_KEY = "-PREVIEW HEIGHT KEY-"
ALPHA_KEY = "-ALPHA KEY-"
PREVIEW_KEY_LIST = [PREVIEW_LOC_X_KEY, PREVIEW_LOC_Y_KEY, PREVIEW_WIDTH_KEY, PREVIEW_HEIGHT_KEY, ALPHA_KEY]

# Button Text
START_PREVIEW = "Start Preview"
STOP_PREVIEW = "Stop Preview"

PREVIEW_LOC_X = 0
PREVIEW_LOC_Y = 0
PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 480
PREVIEW_ALPHA = 255
# Opacity, or Alpha (range 0 (invisible) to 255 (opaque))

PREVIOUS_CAMERA_PREVIEW_X = 0
PREVIOUS_CAMERA_PREVIEW_Y = 0

# Displace Pseudo Window to make it easier to grab/see (in pixels?)
PREVIEW_WINDOW_OFFSET = 30

# Xlib Constants
# Default Screen Index, 0 here.
# Assumes one monitor is connected to Raspberry Pi
DEFAULT_SCREEN_INDEX = 0

# CAMERA CONTROL CONSTANTS
EXPOSURE_MODE_GROUP = "RADIO_EXPOSURE_MODE"
EXPOSURE_AUTO_KEY = "-EXPOSURE AUTO-"
EXPOSURE_MANUAL_KEY = "-EXPOSURE MANUAL-"
MANUAL_SHUTTER_MS_KEY = "-MANUAL SHUTTER MS-"
EXPOSURE_STATUS_KEY = "-EXPOSURE STATUS-"
EXPO_SETTLE_TIME = 2 # in seconds
EXPO_SETTLE_TIME_KEY = "-EXPO SETTLE TIME-"
APPLY_EXPOSURE_BUTTON = "Apply Exposure"
USE_AUTO_WB_BUTTON = "Use Auto WB"
AUTO_WB_LOCK_BUTTON = "Auto WB + Lock"
WB_RED_GAIN_STATUS_KEY = "-WB RED GAIN STATUS-"
WB_BLUE_GAIN_STATUS_KEY = "-WB BLUE GAIN STATUS-"
CAMERA_CONTROL_NOTE_KEY = "-CAMERA CONTROL NOTE-"

is_running_experiment = False
# Camera access lock to avoid preview/still races
CAMERA_LOCK = threading.Lock()

# Numeric-only inputs to guard
NUMERIC_KEYS = [
    "-ROTATION_INPUT-",
    "-PIC_WIDTH_INPUT-",
    "-PIC_HEIGHT_INPUT-",
    "-PREVIEW LOC X KEY-",
    "-PREVIEW LOC Y KEY-",
    "-PREVIEW WIDTH KEY-",
    "-PREVIEW HEIGHT KEY-",
    "-ALPHA KEY-",
    "-EXPO SETTLE TIME-",
    "-MANUAL SHUTTER MS-",
    *ET.ROUND_INPUT_KEY_LIST,
]

# Small-slice sleep so Stop is responsive
def sleep_with_stop(total_seconds, stop_event, chunk=0.25):
    elapsed = 0.0
    while elapsed < total_seconds and not stop_event.is_set():
        wait = min(chunk, total_seconds - elapsed)
        time.sleep(wait)
        elapsed += wait


def sleep_with_stop_and_pause(total_seconds, stop_event, pause_event, chunk=0.25):
    elapsed = 0.0
    while elapsed < total_seconds and not stop_event.is_set():
        while pause_event.is_set() and not stop_event.is_set():
            time.sleep(min(chunk, 0.1))
        if stop_event.is_set():
            break
        wait = min(chunk, total_seconds - elapsed)
        time.sleep(wait)
        elapsed += wait
    return not stop_event.is_set()


def settle_camera_gain(camera, max_wait_seconds=6.0, poll_seconds=0.5, epsilon=0.02):
    """
    Wait briefly for gain values to stabilize without risking an infinite loop.
    """
    prev_value = None
    start_time = time.monotonic()

    while time.monotonic() - start_time < max_wait_seconds:
        try:
            current_value = float(camera.digital_gain)
        except Exception:
            break

        print(f"digital_gain: {current_value}")
        if prev_value is not None and abs(current_value - prev_value) <= epsilon:
            break
        prev_value = current_value
        time.sleep(poll_seconds)

# ==== USER DEFINED FUNCTIONS =====

# Define function, run_relative(direction, values)
def run_relative(direction, values):
    # Converts input buttons (direction) into GCODE String,
    #  then calls run_gcode from printer module (not implemented in this demo)
    # Inputs: takes string direction (X+, X-, Y+, Y-, Z+, or Z-)
    #         values from window.read()

    # For debugging, uncomment to see if the direction (event) and values are being passed correctly
    # print("direction:", direction)
    # print("values:", values)

    # Initialize move_amount to 0.00
    move_amount = DEFAULT_DISTANCE

    # Initialize relative_coordinates variable to direction and 0.00 (example: G0X0.00, no movements)
    relative_coordinates = "{}{}".format(direction, move_amount)

    # For debugging, uncomment to see if the formatting matches the example
    # print("relative_coordinates:", relative_coordinates)

    # For debugging, uncomment to see the move_amount before the if/elif chain
    # print("move_amount (before):", move_amount)

    # Use if/elif chain to check which radio button is true (0.1, 1, or 10)
    # If values[-REL_TENTH-] == True
    #  Example If 0.1 true, change relative coordinates to X-0.10
    # else if the values of relative one is True
    #  Make movement amount into 1.00
    # else if the values of relative ten is True
    #  Make movement amount into 1.00
    if values[RELATIVE_TENTH_KEY] == True:
        # print(RELATIVE_TENTH_KEY, "is active")
        # Extract only the float number, ignoring the "mm"
        move_amount = RELATIVE_TENTH_TEXT[0:-2]
    elif values[RELATIVE_ONE_KEY] == True:
        # print(RELATIVE_ONE_KEY, "is active")
        move_amount = RELATIVE_ONE_TEXT[0:-2]
    elif values[RELATIVE_TEN_KEY] == True:
        # print(RELATIVE_TEN_KEY, "is active")
        move_amount = RELATIVE_TEN_TEXT[0:-2]

    # For debugging, uncomment to see the move_amount after the if/elif chain. Did it change?
    # print("move_amount (after):", move_amount)

    #  Use string formatting to create GCode string (example: G0X-1.00)
    relative_coordinates = "G0{}{}".format(direction, move_amount)

    print("relative_coordinates:", relative_coordinates)

    # This is where you would run the GCode
    # Run Relative Mode
    printer.run_gcode("G91")
            
    # Run relative_coordinates GCODE created in this function
    printer.run_gcode(relative_coordinates)
#   TODO: Extruder Speed Adjustment


# define get_current_location_manager()
# print("===================================")
# print("You pressed Get Current Location!")
# printer.run_gcode("M114")
# serial_string = printer.get_serial_data()
# if GCL.does_location_exist_m114(serial_string) == True:
    # current_location_dictionary, is_location_found = GCL.parse_m114(serial_string)
    # print(current_location_dictionary)
    # printer.printer.flush()
# else:
    # print("Location Not Found, Try Again")
    # printer.printer.flush()
# TODO: Test out flush, then M114, will this prevent having to do it twice?
#       Update: No, it doesn't help.
# Algorithm:
#  Flush, run M114, set serial data, check, make it run twice
#   if location not found, run again?

# TODO: Include picamera settings

# Thread version
# Define function start_experiment(event, values)
def run_experiment(event, values, thread_event, camera, preview_win_id):
    """
    Description: Runs experiment to take a picture, video, or preview (do nothing)
    
    Input: PySimpleGUI window event and values
    """
    # global camera
    print("run_experiment")
    
    if camera.preview:
        camera.stop_preview()
        
    
    
    # Get CSV Filename
    csv_filename = values[OPEN_CSV_FILEBROWSE_KEY]
    
    # Get Path List from CSV
    path_list = P.get_path_list_csv(csv_filename)
    
    # Get GCODE Location List from path_list
    gcode_string_list = P.convert_list_to_gcode_strings(path_list)
    
    # Go into Absolute Positioning Mode
    printer.run_gcode(C.ABSOLUTE_POS)
    
    folder_path = None
    # Create New Folder If not in "Preview" Mode
    if values[EXP_RADIO_PREVIEW_KEY] == False:
        folder_path = P.create_and_get_folder_path()
        print("Not in Preview Mode, creating folder:", folder_path)
        # Initialize unique CSV camera settings file
        GCS.SAVE_CSV_FOLDER = folder_path
        GCS.init_csv_file()
    
    # Create While loop to check if thread_event is not set (closing)
    count_run = 0
    while not thread_event.is_set():
        
        # TODO: Put in the rest of the code for Pic, Video, Preview from 3dprinter_start_experiment or prepare_experiment
        print("=========================")
        print("Run #", count_run)
        
        well_number = 1
        sleep_with_stop(10, thread_event)
        
        for location in gcode_string_list:
            if thread_event.is_set():
                break
            printer.run_gcode(location)
            print("Going to Well Number:", well_number)
            sleep_with_stop(4, thread_event)
            if values[EXP_RADIO_PREVIEW_KEY] == True:
                print("Preview Mode is On, only showing preview camera \n")
                # camera.start_preview(fullscreen=False, window=(30, 30, 500, 500))
                # time.sleep(5)
                
                # camera.stop_preview()
            elif values[EXP_RADIO_VID_KEY] == True:
                print("Recording Video Footage")
                if folder_path:
                    file_full_path = P.get_file_full_path(folder_path, well_number)
                # TODO: Change to Video Captures
            elif values[EXP_RADIO_PIC_KEY] == True:
                print("Taking Pictures Only")
                if folder_path:
                    file_full_path = P.get_file_full_path(folder_path, well_number, total_wells=len(gcode_string_list))
                    get_well_picture(camera, file_full_path)
                    data_row = GCS.gen_cam_data(file_full_path, camera)
                    GCS.append_to_csv_file(data_row)
                
                # Return to streaming resolution: 640 x 480 (or it will crash)
                # Bug: Crashes anyway because of threading
                #camera.resolution = (VID_WIDTH, VID_HEIGHT)
                # TODO: Look up Camera settings to remove white balance (to deal with increasing brightness)
            # May implement the following to break out of loop first. Helpful for lots of wells
            """    
            if is_running_experiment == False:
                print("Stopping Experiment...")
                return
            """
            well_number += 1
        
        count_run += 1
        
        # Use For Loop to go through each location
        # TODO: Preview doesn't show preview camera
        # Original
        # for location in gcode_string_list:
            # # print(location)
            # printer.run_gcode(location)
            # time.sleep(5)
        
        
    print("=========================")
    print("Experiment Stopped")
    print("=========================")
    global is_running_experiment
    is_running_experiment = False


def run_experiment2(event, values, thread_event, pause_event, camera, preview_win_id):
    """
    Description: Runs experiment to take a picture, video, or preview (do nothing)
    
    Input: PySimpleGUI window event and values
    """
    # global camera
    global is_running_experiment
    print("run_experiment with round scheduling")
    
    if camera.preview:
        camera.stop_preview()
    
    round_count, interval_seconds = ET.get_round_settings(values)
    start_time = time.monotonic()

    # Get CSV Filename
    csv_filename = values[OPEN_CSV_FILEBROWSE_KEY]
    
    # Get Path List from CSV
    path_list = P.get_path_list_csv(csv_filename)
    
    # Get GCODE Location List from path_list
    gcode_string_list = P.convert_list_to_gcode_strings(path_list)
    total_wells = len(gcode_string_list)
    if total_wells == 0:
        print("Selected CSV has no well locations. Stopping experiment.")
        is_running_experiment = False
        return
    
    # Go into Absolute Positioning Mode
    printer.run_gcode(C.ABSOLUTE_POS)
    
    folder_path = None
    # Create New Folder If not in "Preview" Mode
    if values[EXP_RADIO_PREVIEW_KEY] == False:
        dest_folder = PIC_SAVE_FOLDER
        folder_path = P.create_and_get_folder_path2(dest_folder)
        print("Not in Preview Mode, creating folder:", folder_path)
        GCS.SAVE_CSV_FOLDER = folder_path
        GCS.init_csv_file()
    
    completed_rounds = 0
    while completed_rounds < round_count and not thread_event.is_set():
        # Honor pause requests
        while pause_event.is_set() and not thread_event.is_set():
            time.sleep(0.1)
        if thread_event.is_set():
            break

        current_round = completed_rounds + 1
        print("=========================")
        print(f"Round {current_round} of {round_count}")
        well_number = 1
        round_complete = True

        for location in gcode_string_list:
            # Respect pause while iterating wells
            while pause_event.is_set() and not thread_event.is_set():
                time.sleep(0.1)
            if thread_event.is_set():
                round_complete = False
                break

            printer.run_gcode(location)
            print("Going to Well Number:", well_number)
            if well_number == 1:
                print(f"Pausing at well {well_number} for 10 seconds")
                if not sleep_with_stop_and_pause(10, thread_event, pause_event):
                    round_complete = False
                    break
                print("pause is complete")
            else:
                if not sleep_with_stop_and_pause(4, thread_event, pause_event):
                    round_complete = False
                    break

            if values[EXP_RADIO_PREVIEW_KEY] == True:
                print("Preview Mode is On, only showing preview camera \n")
                # camera.start_preview(fullscreen=False, window=(30, 30, 500, 500))
                # time.sleep(5)
                
                # camera.stop_preview()
            elif values[EXP_RADIO_VID_KEY] == True:
                print("Recording Video Footage")
                if folder_path:
                    file_full_path = P.get_file_full_path(folder_path, well_number, total_wells=total_wells)
                # TODO: Change to Video Captures
                # camera.capture(file_full_path)
            elif values[EXP_RADIO_PIC_KEY] == True:
                print("Taking Pictures Only")
                if folder_path:
                    file_full_path = P.get_file_full_path(folder_path, well_number, total_wells=total_wells)
                
                if folder_path:
                    get_well_picture(camera, file_full_path)
                    data_row = GCS.gen_cam_data(file_full_path, camera)
                    GCS.append_to_csv_file(data_row)

            well_number += 1

        if not round_complete or thread_event.is_set():
            break

        completed_rounds += 1
        print(f"Completed round {completed_rounds} of {round_count}")

        if completed_rounds >= round_count:
            break

        if interval_seconds > 0:
            next_round = completed_rounds + 1
            print(f"Will wait {interval_seconds} sec before round {next_round}.")
            if not sleep_with_stop_and_pause(interval_seconds, thread_event, pause_event):
                break
            print(f"Done waiting {interval_seconds} sec")
        else:
            print("Round interval is 0 seconds, starting next round immediately.")

    elapsed_seconds = time.monotonic() - start_time
    print("=========================")
    print("Experiment Stopped")
    print("=========================")
    print(f"Ran experiment for {elapsed_seconds:.1f} seconds, or {elapsed_seconds/60:.1f} minutes, or {elapsed_seconds/60/60:.1f} hours")
    print(f"Completed {completed_rounds} round(s) out of {round_count}")
    print(f"Data saved to: {folder_path}")
    print("-------------------------")
    is_running_experiment = False

# Takes in event and values to check for radio selection (Pictures, Videos, or Preview)
# Takes in CSV filename or location list generated from opening CSV file
#    Use get_path_list_csv(csv_filename) and convert_list_to_gcode_strings(path_list) from prepare_experiment module
# Create section for camera setup (or create another function to set camera settings)
#  Create function to return camera settings to default (for preview?)
# Create section for video camera setup (length of time to record)
# Goes to each location in list and takes picture, video, or nothing
#   Use for loop to go through each location list
#     Use if statement chain for radio buttons
#       If Picture, take picture. If Video, take video. If Preview, only go there.
# TODO: Include input for number of runs or length of time to run? (Use my Arduino strategy, put in the camera for loop
#       Recommend number of runs first, then implement countdown algorithm?
# TODO: Test picture/video capabilities while camera feed is running. Update, picture works


# Non-thread version
def run_experiment_gui(main_values, camera):
    # Inputs: values or csv_filename?
    
    global is_running_experiment
    
    # Get paths from CSV file
    print("run_experiment")
    
    camera.stop_preview()
    
    
    # Get CSV Filename
    csv_filename = main_values[OPEN_CSV_FILEBROWSE_KEY]
    
    # Get Path List from CSV
    path_list = P.get_path_list_csv(csv_filename)
    
    # Get GCODE Location List from path_list
    gcode_string_list = P.convert_list_to_gcode_strings(path_list)
    gcode_string_list_len = len(gcode_string_list)
    print(f"gcode_string_list_len: {gcode_string_list_len}")
    
    # Go into Absolute Positioning Mode
    printer.run_gcode(C.ABSOLUTE_POS)
    
    # Move to first well
    print("Moving to first well and waiting a few seconds")
    printer.run_gcode(gcode_string_list[0])
    
    # Wait to go to well
    time.sleep(3)
    print("Done waiting to go to WELL")
    
    
    # setup_picture_camera_settings(camera)
    # setup_default_camera_settings(camera)
    
    
    # Change camera resolution
    # Sensor resolution (Pi Camera 2, 3280x2464)
    # Change resolution to largest resolution for taking pictures
    # Change Image Capture Resolution
    pic_width = PIC_WIDTH
    pic_height = PIC_HEIGHT

    camera.resolution = (pic_width, pic_height)
    
    # Sleep time for exposure mode
    # time.sleep(expo_wait_time)
    
    
    # Setup separate GUI
    # setup theme
    sg.theme("Light Brown 3")
    
    # setup layout of new GUI (one window with a single button)
    layout_exp = [[sg.Button("Stop Experiment", size=(20,20))]]

    # setup window for new GUI
    window_exp = sg.Window("Experiment GUI Window", layout_exp, finalize=True)
    
    # Create New Folder If not in "Preview" Mode
    if main_values[EXP_RADIO_PREVIEW_KEY] == False:
        folder_path = P.create_and_get_folder_path()
        print("Not in Preview Mode, creating folder:", folder_path)
    
    # Setup how long to wait before moving to next well (and GUI loop)
    time_to_wait = 2000 # in millisec
    
    # Initialize index for going through gcode_string_list
    index = 0
    # ---- EVENT LOOP ----
    while True:
        event, values = window_exp.read(timeout=time_to_wait)
        
        # Run Experiment
        # print(f"Index: {index}")
        # print(gcode_string_list[index])
        
        well_number = index + 1
        print(f"Well Number: {well_number}")
        
        printer.run_gcode(gcode_string_list[index])
        # Wait to go to well
        time.sleep(2)
        
        if main_values[EXP_RADIO_PREVIEW_KEY] == True:
            print("Preview Mode is On, only showing preview camera \n")
            # camera.start_preview(fullscreen=False, window=(30, 30, 500, 500))
            # time.sleep(5)
            
            # camera.stop_preview()
        elif main_values[EXP_RADIO_VID_KEY] == True:
            print("Recording Video Footage")
            file_full_path = P.get_file_full_path(folder_path, well_number)
            # TODO: Change to Video Captures
            # camera.capture(file_full_path)
        elif main_values[EXP_RADIO_PIC_KEY] == True:
            print("Taking Pictures Only")
            file_full_path = P.get_file_full_path(folder_path, well_number)
            # print(file_full_path)
            
            get_well_picture(camera, file_full_path)
            
            # camera.capture(file_full_path)
            # TODO: Look up Camera settings to remove white balance (to deal with increasing brightness)
            time.sleep(2)
            
            
        
        
        # If index is at the end of the list, reset it. else increment it.
        if index == (gcode_string_list_len - 1):
            index = 0
        else:
            index += 1
            
        
        
        if event.startswith("Stop"):
            print("You pressed Stop. Stopping experiment")
            break
    
    window_exp.close()
    
    # Change resolution back to video stream
    camera.resolution = (VID_WIDTH, VID_HEIGHT)
    # time.sleep(expo_wait_time)
    
    # setup_default_camera_settings(camera)
    
    is_running_experiment = False

    
    # 
    pass


# Define function get_gcode_string_list(values)

def get_gcode_string_list(values):
    """
    Description: Takes CSV File from values (GUI Data), returns gcode_string_list
    Input: values, a dictionary from PySimpleGUI Window Reads
    Return/Output: GCode String List for well location.
    """
    # Get CSV Filename
    csv_filename = values[OPEN_CSV_FILEBROWSE_KEY]
    
    # Get Path List from CSV
    path_list = P.get_path_list_csv(csv_filename)
    
    # Get GCODE Location List from path_list
    gcode_string_list = P.convert_list_to_gcode_strings(path_list)
    
    # Return gcode_string_list
    
    pass


# Define function, get_sample(folder_path_sample, values)

def get_sample(folder_path_sample, well_number, values):
    """
    Description: Takes Pic/Vid/Preview Radio Values, then takes a
                 picture, video, or preview (do nothing), stores into
                 folder_path_sample
    Inputs:
      - values, a dictionary from PySimpleGUI Window Reads. The main focus are the Radio values for the Pic/Vid/Preview.
      - folder_path_sample, a string holding the unique folder path for the samples (prevents accidental overwrite)
    Return/Output: Doesn't return anything. TODO: Return True/False if failed or successful?
    """
    
    # Create Unique Filename, call get_file_full_path(folder_path, well_number)
    # Check Experiment Radio Buttons
    #  If Picture is True, take a picture. Save with unique filename
    #  If Video is True, take a video. Save with unique filename
    #  If Preview is True, do nothing or print "Preview Mode"
    
    pass


def get_video(camera):
    
    # Create Unique Filename
    current_time = datetime.now()
    current_time_str = current_time.strftime("%Y-%m-%d_%H%M%S")
    video_ext = getattr(camera, "preferred_video_extension", ".h264")
    if not isinstance(video_ext, str) or len(video_ext) == 0:
        video_ext = ".h264"
    if not video_ext.startswith("."):
        video_ext = f".{video_ext}"
    filename = f"video_{current_time_str}{video_ext}"
    
    # Set Recording Time (in seconds)
    recording_time = int(1 * 5)
    
    try:
        camera.start_recording(filename)
        camera.wait_recording(recording_time)
        camera.stop_recording()
    except Exception as exc:
        print(f"Video recording failed: {exc}")
        return
    
    print(f"Recorded Video: {filename}")


def capture_still(camera, file_full_path):
    """Safely capture a still by pausing preview and restoring resolution."""
    backend_name = str(getattr(camera, "backend_name", ""))
    is_usb_backend = ("USBCameraBackend" in backend_name)

    with CAMERA_LOCK:
        was_previewing = bool(camera.preview)
        if was_previewing and not is_usb_backend:
            camera.stop_preview()
        original_res = camera.resolution
        success = False
        try:
            if is_usb_backend:
                # USB cameras often behave better when capture uses current stream settings.
                camera.capture(file_full_path)
            else:
                camera.resolution = (PIC_WIDTH, PIC_HEIGHT)
                camera.capture(file_full_path)
            success = True
        except Exception as exc:
            print(f"Still capture failed: {exc}")
        finally:
            try:
                camera.resolution = original_res
            except Exception:
                pass
            if was_previewing and not is_usb_backend:
                preview_window = (PREVIEW_LOC_X, PREVIEW_LOC_Y, PREVIEW_WIDTH, PREVIEW_HEIGHT)
                camera.start_preview(alpha=PREVIEW_ALPHA, fullscreen=False, window=preview_window)
        return success


def get_picture(camera):
    # TODO: Change variables here to Global to match changes in Camera Tab
    # Take a Picture, 12MP: 4056x3040
    pic_width = PIC_WIDTH
    pic_height = PIC_HEIGHT
    unique_id = get_unique_id()
    pic_save_name = f"test_{unique_id}_{pic_width}x{pic_height}.jpg"
    
    pic_save_full_path = f"{PIC_SAVE_FOLDER}/{pic_save_name}"
    
    if capture_still(camera, pic_save_full_path):
        print(f"Saved Image: {pic_save_full_path}")
    pass


def get_well_picture(camera, file_full_path):
    # TODO: Change variables here to Global to match changes in Camera Tab
    # Take a Picture, 12MP: 4056x3040
    pic_width = PIC_WIDTH
    pic_height = PIC_HEIGHT
    # unique_id = get_unique_id()
    # pic_save_name = f"well{well_number}_{unique_id}_{pic_width}x{pic_height}.jpg"
    
    if capture_still(camera, file_full_path):
        print(f"Saved Image: {file_full_path}")
    pass



def get_x_pictures(x, delay_seconds, camera):
    
    # Run loop x times
    for i in range(x):
    
        # Create Unique ID
        unique_id = get_unique_id()
        # Create Save Name from Unique ID
        pic_save_name = f"test_{unique_id}_{PIC_WIDTH}x{PIC_HEIGHT}.jpg"
        # Create Full Save Path using Save Name and Save Folder
        pic_save_full_path = f"{PIC_SAVE_FOLDER}/{pic_save_name}"
        # Capture Image
        if capture_still(camera, pic_save_full_path):
            # Print that picture was saved
            print(f"Saved Image: {pic_save_full_path}")
        # Wait Delay Amount
        time.sleep(delay_seconds)
    
    print(f"Done taking {x} pictures.")
    
    pass

# Define function to create unique text string using date and time.
def get_unique_id():
    current_time = datetime.now()
    unique_id = current_time.strftime("%Y-%m-%d_%H%M%S")
    # print(f"unique_id: {unique_id}")
    return unique_id


# Define function to check an InputText key for digits only
def check_for_digits_in_key(key_str, window, event, values):
    
    if event == key_str and len(values[key_str]) and values[key_str][-1] not in ('0123456789'):
            # delete last char from input
            # print("Found a letter instead of a number")
            window[key_str].update(values[key_str][:-1])


def create_z_stack(z_start, z_end, z_increment, save_folder_location, camera):
    # Assumes all inputs are floating or integers, no letters!
    print("create_z_stack")
    print("Pausing Video Stream")

    # GCODE Position, goes fastest
    position = "G0"

    # Go into Absolute Mode, "G90"
    # Run GCODE to go into Absolute Mode
    printer.run_gcode(C.ABSOLUTE_POS)

    # Will use absolute location mode to go to each z
    # Alternative, you could use relative and get current location to get z value.
    # Test: Use Get Current Location to compare expected vs actual z.

    # Create Unique folder to save into save_folder_location
    save_folder_path = f"{save_folder_location}/z_stack_{get_unique_id()}"
    
    # Check if folder exists, if not, create it
    if not os.path.isdir(save_folder_path):
        print("Folder Does NOT exist! Making New Folder")
        os.mkdir(save_folder_path)
    else:
        print("Folder Exists")
    
    # print(f"save_folder_path: {save_folder_path}")
    
    # Go to first location, wait x seconds?

    # Mark where we think z_focus is?

    for z in np.arange(z_start, z_end+z_increment, z_increment):
        print(f"z: {z}")
        # Make sure number gets rounded to 2 decimal places (ex: 25.23)

        # Round z to 2 decimal places
        z_rounded = round(z, 2)
        # Fill out with zeroes until 5 characters long, example: 1.2 becomes 01.20
        # For easier viewing purposes depending on OS.
        z_rounded_str = f"{z_rounded}".zfill(5) 

        # Convert z to GCODE
        # GCODE Format: G0Z2.34
        gcode_str = f"{position}Z{z_rounded}"

        print(f"gcode_str: {gcode_str}")

        # Go to z location using printer_connection module's run_gcode
        # Possible bug, could this module be used elsewhere? This code may have to run in the same location as the GUI.
        printer.run_gcode(gcode_str)
        # Wait x seconds for extruder to get to location.
        time.sleep(2)


        # Take Picture and save to folder location
        save_file_name = f"_image_{z_rounded_str}_.jpg"
        save_full_path = f"{save_folder_path}/{save_file_name}"
        
        # Change to max resolution
        camera.resolution = PIC_RES
        
        
        camera.capture(save_full_path)
        
        # Change back to streaming resolution
        camera.resolution = VID_RES

    
    print(f"Done Creating Z Stack at {save_folder_path}")

    pass


# Define function to get current location
def get_current_location():
    printer.run_gcode("M114")
    serial_string = printer.get_serial_data()
    if GCL.does_location_exist_m114(serial_string) == True:
        current_location_dictionary, is_location_found = GCL.parse_m114(serial_string)
        print(current_location_dictionary)
        # printer.printer.flush()
    else:
        print("Location Not Found, Try Again")
    pass
    

def get_current_location2():
    print("Getting Current Location...")
    
    # Init result with negative values for error checking
    # If negative value, then location was not found
    result = {"X": -1.00, "Y": -1.00, "Z": -1.00}
    
    # Number of attempts to check for location (how many times to run for loop)
    num_location_checks = 10
    
    # Number of location grabs until that one is accepted (in case of outdated location)
    num_until_location_accepted = 1
    
    # Init location_found_counter (want loc to be found at least once since old one is stored)
    location_found_counter = 0
    
    num_searches = 0
    for i in range(num_location_checks):
        num_searches += 1
        # Uncomment print statement for debugging
        # print(f"Location Search Attempt: {i}")
        # Run M114 GCODE
        printer.run_gcode("M114")
        # Make GUI wait for 3D printer to receive and process command.
        # May need to make this adjustable in the future.
        time.sleep(1)
        serial_string = printer.get_serial_data2()
        if GCL.does_location_exist_m114(serial_string) == True:
            
            current_location_dictionary, is_location_found = GCL.parse_m114(serial_string)
            
            if location_found_counter == 0:
                location_found_counter += 1
                # Uncomment print statement for debugging
                # print("Location Found, but might be outdated. Trying again")
                continue
            elif location_found_counter >= num_until_location_accepted:
                result = current_location_dictionary
                print("Location Found, Stopping Search.")
                break
        else:
            print("Location Not Found, Trying Again...")
            # If location not found, wait a second in case there is a buffer issue?
            # If no data found, get_serial_data2 ran at least 20 times, so used default empty string
            #   Should try again
            """
            print(f"Data Found: {serial_string}")
            if len(serial_string) == 0:
                print("No data found")
            """
            time.sleep(1)
            continue
        
        # Get Serial Data
        # If location exist in serial string, increment location_found_counter by 1, start while loop again
        #   If loc exist and counter is 1, save location
        # If location does not exist, don't increment, start while loop again
    
    print(f"Number of Location Retrieval Attempts: {num_searches}")
    print("**Note: If all coord are -1.00, then location was not found")
    print(f"Location: {result}")
    return result


# Save current location
# Alt: Save to List instead, then have "Save" button?
# Ask user to choose file name and location first?
# Can only save loc if filename is chosen?
def save_current_location():
    print("save_current_location")
    cur_loc_dict = get_current_location2()
    print(f"cur_loc_dict: {cur_loc_dict}")

    # Make newline be blank, prevents extra empty lines from happening
    f = open(TEMP_FULL_PATH, 'a', newline="")
    writer = csv.writer(f)

    # Possible to check for headers row?
    # headers = ["X", "Y", "Z"]
    row = [0]

    for key, value in cur_loc_dict.items():
        print(key, value)
        row.append(value)

    print(row)

    # writer.writerow(headers)
    writer.writerow(row)

    f.close()
    print("File Saved")


# === Start Camera Preview Window Functions ===
def get_max_screen_resolution():
    """
    Gets Max Screen Resolution,
    returns max_screen_width, max_screen_height in pixels
    """
    max_screen_width = 0
    max_screen_height = 0
    
    d = Display()
    
    info = d.screen(DEFAULT_SCREEN_INDEX)
    
    max_screen_width = info.width_in_pixels
    max_screen_height = info.height_in_pixels
    
    # print(f"Width: {max_screen_width}, height: {max_screen_height}")
    """
    for screen in range(0,screen_count):
        info = d.screen(screen)
        print("Screen: %s. Default: %s" % (screen, screen==default_screen))
        print("Width: %s, height: %s" % (info.width_in_pixels,info.height_in_pixels))
    """
    
    d.close()
    
    return max_screen_width, max_screen_height


def get_xy_loc_of_all_windows():
    disp = Display()
    root = disp.screen().root
    children = root.query_tree().children
    
    loc_x_list = []
    loc_y_list = []
    
    for win in children:
        winName = win.get_wm_name()
        pid = win.id
        x, y, width, height = get_absolute_geometry(win, root)
        
        loc_x_list.append(x)
        loc_y_list.append(y)
    
    disp.close()
    
    return loc_x_list, loc_y_list


def get_unique_xy_loc():
    loc_x_list, loc_y_list = get_xy_loc_of_all_windows()
    
    # Get unique values from list only, remove negatives
    x_exclude_list = list(set(loc_x_list))
    y_exclude_list = list(set(loc_y_list))
    
    # print("After Set Stuff")
    # print(f"x_exclude_list: {x_exclude_list}")
    # print(f"y_exclude_list: {y_exclude_list}")
    
    # Random Int selection for x and y, exclude unique values above,
    # max would be max screen resolution
    
    # Get max screen width and height
    max_screen_width, max_screen_height = get_max_screen_resolution()
    
    # Use set subtraction to create list of integers for random choice
    # (is faster than using a for loop to remove numbers)
    
    x_start = random.choice(list(set([x for x in range(0, max_screen_width)]) - set(x_exclude_list)))
    y_start = random.choice(list(set([y for y in range(0, max_screen_height)]) - set(y_exclude_list)))
    # print(f"x_start: {x_start}")
    # print(f"y_start: {y_start}")
    
    return x_start, y_start


def get_window_pid(x_start, y_start):
    print("***get_window_pid()***")
    disp = Display()
    root = disp.screen().root
    children = root.query_tree().children
    
    result_pid = 0
    
    for win in children:
        winName = win.get_wm_name()
        pid = win.id
        x, y, width, height = get_absolute_geometry(win, root)
        
        if x == x_start and y == y_start:
            """
            print("======Children=======")
            print(f"winName: {winName}, pid: {pid}")
            print(f"x:{x}, y:{y}, width:{width}, height:{height}")
            """
            # print(f"wm: {win.get_window_title()}")
            
            # Move Window x = 50, y = 20
            # win.configure(x=x+50)
            # win.configure(x=400, y=36)
            
            # Set Window Name to "Camera Preview Window"
            # win.set_wm_name("Camera Preview Window")
            
            result_pid = pid
            break
    
    disp.close()
    
    return result_pid


def get_window_location_from_pid(search_pid):
    # print("get_window_location_from_pid")
    # print(f"search_pid: {search_pid}")
    
    try:
        disp = Display()
        root = disp.screen().root
        children = root.query_tree().children
        
        x_win, y_win = 0, 0
        
        for win in children:
            try:
                winName = win.get_wm_name()
            except Exception:
                continue
            pid = win.id
            x, y, width, height = get_absolute_geometry(win, root)
            
            if pid == search_pid:
                x_win = x
                y_win = y
                break
        disp.close()
        return x_win, y_win
    except Exception:
        # If window vanished or X error, return default
        return PREVIEW_LOC_X, PREVIEW_LOC_Y


def move_window_pid(search_pid, x_new, y_new):
    print("***move_window_pid()***")
    # print(f"search_pid: {search_pid}")
    disp = Display()
    root = disp.screen().root
    children = root.query_tree().children
    
    for win in children:
        winName = win.get_wm_name()
        pid = win.id
        x, y, width, height = get_absolute_geometry(win, root)
        
        if pid == search_pid:
            """
            print("======Children=======")
            print(f"winName: {winName}, pid: {pid}")
            print(f"x:{x}, y:{y}, width:{width}, height:{height}")
            """
            
            print(f"Moving Window Name: {winName}, pid: {pid}")
            win.configure(x=x_new, y=y_new)
            
            break
    
    disp.close()


def change_window_name(search_pid, new_window_name):
    print("***change_window_name()***")
    # Change Window Name of Specific PID
    # print(f"search_pid: {search_pid}")
    disp = Display()
    root = disp.screen().root
    children = root.query_tree().children
    
    for win in children:
        winName = win.get_wm_name()
        pid = win.id
        x, y, width, height = get_absolute_geometry(win, root)
        
        if pid == search_pid:
            """
            print("======Children=======")
            print(f"winName: {winName}, pid: {pid}")
            print(f"x:{x}, y:{y}, width:{width}, height:{height}")
            """
            
            win.set_wm_name(new_window_name)
            
            break
    disp.close()


def get_absolute_geometry(win, root):
    """
    Returns the (x, y, height, width) of a window relative to the
    top-left of the screen.
    """
    geom = win.get_geometry()
    (x, y) = (geom.x, geom.y)
    
    # print("Start")
    # print(f"x: {x}, y: {y}")
    
    while True:
        parent = win.query_tree().parent
        pgeom = parent.get_geometry()
        x += pgeom.x
        y += pgeom.y
        
        if parent.id == root.id:
            # print("parent id matches root id. Breaking...")
            break
        win = parent
    
    # print("End")
    # print(f"x: {x}, y: {y}")
    return x, y, geom.width, geom.height
# === End Camera Preview Window Functions ===


# === Start Camera Settings Functions ===

def setup_picture_camera_settings(camera):
    print("Setting up picture camera settings")
    
    # Turn Exposure mode back on so camera can adjust to new light
    camera.exposure_mode = "auto"
    
    # Turn off camera led
    camera.led = False
    
    # Camera Framerate
    camera.framerate = 30
    time.sleep(1)
    
    # Setup default resolution
    # Sensor resolution (Pi Camera 2, 3280x2464)
    # width = 640
    # height = 480
    camera.resolution = VID_RES
    
    # ISO: Image Brightness
    # 100-200 (daytime), 400-800 (low light)
    iso_number = 100
    camera.iso = iso_number
    
    time.sleep(10)
    
    # Contrast
    # Takes values between 0-100
    contrast_number = 50
    camera.contrast = contrast_number
    
    # Automatic White Balance
    camera.awb_mode = "off"
    red_gain = 1.5
    blue_gain = 1.8
    camera.awb_gains = (red_gain, blue_gain)
    
    
    
    # Exposure Mode
    # camera.framerate = 30
    # camera.shutter_speed = 33164
    camera.shutter_speed = camera.exposure_speed
    camera.exposure_mode = "off"
    # Must let camera sleep so exposure mode can settle on certain values, else black screen happens
    time.sleep(2)
    print("Done setting picture camera settings")
    

def setup_default_camera_settings(camera):
    print("Setting default camera settings")
    
    # Turn Exposure mode back on so camera can adjust to new light
    camera.exposure_mode = "auto"
    
    # Turn off camera led
    camera.led = False
    
    # Camera Framerate
    camera.framerate = 30
    time.sleep(1)
    
    # Setup default resolution
    # Sensor resolution (Pi Camera 2, 3280x2464)
    width = 640
    height = 480
    camera.resolution = (width, height)
    
    # ISO: Image Brightness
    # 100-200 (daytime), 400-800 (low light)
    iso_number = 100
    camera.iso = iso_number
    
    time.sleep(10)
    
    # Contrast
    # Takes values between 0-100
    contrast_number = 50
    camera.contrast = contrast_number
    
    # Automatic White Balance
    camera.awb_mode = "off"
    red_gain = 1.5
    blue_gain = 1.8
    camera.awb_gains = (red_gain, blue_gain)
    
    
    
    # Exposure Mode
    # camera.framerate = 30
    # camera.shutter_speed = 33164
    camera.shutter_speed = camera.exposure_speed
    camera.exposure_mode = "off"
    # Must let camera sleep so exposure mode can settle on certain values, else black screen happens
    time.sleep(2)
    
    print("Done setting default camera settings")
    
    pass


def camera_backend_supports_manual_controls(camera):
    backend_name = str(getattr(camera, "backend_name", "")).strip().lower()
    return "usb" not in backend_name


def get_camera_settle_time_seconds(values):
    settle_value = str(values.get(EXPO_SETTLE_TIME_KEY, EXPO_SETTLE_TIME)).strip()
    if len(settle_value) == 0:
        return EXPO_SETTLE_TIME
    return int(settle_value)


def get_current_exposure_speed_us(camera):
    try:
        exposure_speed = int(getattr(camera, "exposure_speed", 0) or 0)
    except Exception:
        exposure_speed = 0

    if exposure_speed > 0:
        return exposure_speed

    try:
        return int(getattr(camera, "shutter_speed", 0) or 0)
    except Exception:
        return 0


def get_current_shutter_ms(camera):
    exposure_speed_us = get_current_exposure_speed_us(camera)
    if exposure_speed_us <= 0:
        return None
    return max(1, int(round(exposure_speed_us / 1000.0)))


def normalize_awb_gains(gains):
    if not isinstance(gains, (list, tuple)) or len(gains) != 2:
        return None

    try:
        return float(gains[0]), float(gains[1])
    except (TypeError, ValueError):
        return None


def update_exposure_status_text(window, camera):
    exposure_mode = str(getattr(camera, "exposure_mode", "unknown")).lower()

    try:
        shutter_speed_us = int(getattr(camera, "shutter_speed", 0) or 0)
    except Exception:
        shutter_speed_us = 0

    if exposure_mode == "off" and shutter_speed_us > 0:
        status_text = f"Current shutter: {shutter_speed_us / 1000.0:.2f} ms (manual)"
    else:
        exposure_speed_us = get_current_exposure_speed_us(camera)
        if exposure_speed_us > 0:
            status_text = f"Current shutter: {exposure_speed_us / 1000.0:.2f} ms (auto)"
        else:
            status_text = "Current shutter: unavailable"

    window[EXPOSURE_STATUS_KEY].update(status_text)


def update_locked_wb_text(window, gains):
    normalized_gains = normalize_awb_gains(gains)
    if normalized_gains is None:
        window[WB_RED_GAIN_STATUS_KEY].update("Locked Red Gain: --")
        window[WB_BLUE_GAIN_STATUS_KEY].update("Locked Blue Gain: --")
        return

    red_gain, blue_gain = normalized_gains
    window[WB_RED_GAIN_STATUS_KEY].update(f"Locked Red Gain: {red_gain:.3f}")
    window[WB_BLUE_GAIN_STATUS_KEY].update(f"Locked Blue Gain: {blue_gain:.3f}")


def update_camera_control_enabled_state(window, supports_manual_camera_controls, manual_selected):
    controls_disabled = not supports_manual_camera_controls
    window[EXPOSURE_AUTO_KEY].update(disabled=controls_disabled)
    window[EXPOSURE_MANUAL_KEY].update(disabled=controls_disabled)
    window[MANUAL_SHUTTER_MS_KEY].update(disabled=(controls_disabled or not manual_selected))
    window[APPLY_EXPOSURE_BUTTON].update(disabled=controls_disabled)
    window[USE_AUTO_WB_BUTTON].update(disabled=controls_disabled)
    window[AUTO_WB_LOCK_BUTTON].update(disabled=controls_disabled)


def initialize_camera_control_panel(window, camera, supports_manual_camera_controls):
    backend_name = getattr(camera, "backend_name", "unknown")

    if supports_manual_camera_controls:
        is_manual = str(getattr(camera, "exposure_mode", "auto")).lower() == "off"
        if is_manual:
            shutter_ms = get_current_shutter_ms(camera)
            if shutter_ms is not None:
                window[MANUAL_SHUTTER_MS_KEY].update(str(shutter_ms))

        window[EXPOSURE_AUTO_KEY].update(value=(not is_manual))
        window[EXPOSURE_MANUAL_KEY].update(value=is_manual)
        window[CAMERA_CONTROL_NOTE_KEY].update(
            f"Backend: {backend_name}. Use Auto WB on a white card, then click Auto WB + Lock."
        )
        update_camera_control_enabled_state(window, True, is_manual)
        update_exposure_status_text(window, camera)
        update_locked_wb_text(window, None)
        return

    window[EXPOSURE_AUTO_KEY].update(value=True)
    window[EXPOSURE_MANUAL_KEY].update(value=False)
    window[MANUAL_SHUTTER_MS_KEY].update("")
    update_camera_control_enabled_state(window, False, False)
    window[CAMERA_CONTROL_NOTE_KEY].update(
        f"Backend: {backend_name}. Exposure and white balance controls are not supported on this backend."
    )
    window[EXPOSURE_STATUS_KEY].update("Current shutter: unavailable")
    update_locked_wb_text(window, None)


def apply_exposure_settings(values, window, camera, supports_manual_camera_controls):
    if not supports_manual_camera_controls:
        print("Exposure controls are not supported on this camera backend.")
        return

    settle_time = get_camera_settle_time_seconds(values)
    manual_selected = bool(values.get(EXPOSURE_MANUAL_KEY, False))

    if not manual_selected:
        camera.shutter_speed = 0
        camera.exposure_mode = "auto"
        print(f"Auto exposure enabled. Settling for {settle_time} seconds.")
        if settle_time > 0:
            time.sleep(settle_time)
        update_exposure_status_text(window, camera)
        return

    shutter_value = str(values.get(MANUAL_SHUTTER_MS_KEY, "")).strip()
    if len(shutter_value) == 0:
        shutter_ms = get_current_shutter_ms(camera)
        if shutter_ms is None:
            print("Unable to seed manual shutter from the current exposure.")
            return
        window[MANUAL_SHUTTER_MS_KEY].update(str(shutter_ms))
        print(f"Manual shutter was blank. Seeded to {shutter_ms} ms from the current exposure.")
    else:
        shutter_ms = int(shutter_value)
        if shutter_ms <= 0:
            print("Manual shutter must be greater than 0 ms.")
            return

    camera.shutter_speed = shutter_ms * 1000
    camera.exposure_mode = "off"
    print(f"Manual exposure enabled at {shutter_ms} ms. Settling for {settle_time} seconds.")
    if settle_time > 0:
        time.sleep(settle_time)
    update_exposure_status_text(window, camera)


def enable_auto_white_balance(camera, supports_manual_camera_controls):
    if not supports_manual_camera_controls:
        print("White-balance controls are not supported on this camera backend.")
        return

    camera.awb_mode = "auto"
    print("Auto white balance enabled.")


def lock_auto_white_balance(values, window, camera, supports_manual_camera_controls):
    if not supports_manual_camera_controls:
        print("White-balance controls are not supported on this camera backend.")
        return

    settle_time = get_camera_settle_time_seconds(values)
    camera.awb_mode = "auto"
    print(f"Auto white balance settling for {settle_time} seconds before lock.")
    if settle_time > 0:
        time.sleep(settle_time)

    gains = normalize_awb_gains(camera.awb_gains)
    if gains is None:
        print("Unable to read auto white-balance gains.")
        return

    camera.awb_mode = "off"
    camera.awb_gains = gains
    update_locked_wb_text(window, gains)
    print(f"Locked white balance gains: red={gains[0]:.3f}, blue={gains[1]:.3f}")
# === End Camera Settings Functions ===


def start_camera_preview(event, values, camera, preview_win_id):
    print("Starting Preview With Settings")
    if camera.preview:
        camera.stop_preview()
    prev_width = int(values[PREVIEW_WIDTH_KEY])
    prev_height = int(values[PREVIEW_HEIGHT_KEY])
    prev_loc_x = int(values[PREVIEW_LOC_X_KEY])
    prev_loc_y = int(values[PREVIEW_LOC_Y_KEY])
    alpha_val = int(values[ALPHA_KEY])
    
    # Update Global Variables so Pseudo Window has Control
    PREVIEW_LOC_X = prev_loc_x
    PREVIEW_LOC_Y = prev_loc_y
    PREVIEW_WIDTH = prev_width
    PREVIEW_HEIGHT = prev_height
    PREVIEW_ALPHA = alpha_val
    
    # Move Pseudo Window to input location too
    move_window_pid(preview_win_id, prev_loc_x, prev_loc_y - PREVIEW_WINDOW_OFFSET)
    
    camera.start_preview(alpha=alpha_val, fullscreen=False, window=(prev_loc_x, prev_loc_y, prev_width, prev_height))
    
    x_win, y_win = get_window_location_from_pid(preview_win_id)
    print(f"x_win:{x_win}, y_win:{y_win}")


# define main function
def main():
    
    # Temporary Solution: Make pic res/save globally accessible for modification
    global PIC_WIDTH, PIC_HEIGHT, PIC_SAVE_FOLDER, is_running_experiment, easy_rot

    # Setup camera backend (picamera or libcamera/picamera2 via settings).
    backend_name = getattr(C, "CAMERA_BACKEND", "picamera")
    camera_device_index = getattr(C, "CAMERA_DEVICE_INDEX", 0)
    backend_name_norm = str(backend_name).strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    print(f"Camera backend requested: {backend_name} (device: {camera_device_index})")
    try:
        camera = create_legacy_camera(
            backend_name=backend_name,
            rotation=easy_rot,
            preview_res=(VID_WIDTH, VID_HEIGHT),
            device_index=camera_device_index,
        )
    except ValueError:
        # Invalid backend names should fail fast so config issues are obvious.
        raise
    except RuntimeError as exc:
        if backend_name_norm in ("libcamera", "picamera2", "libcam"):
            print(f"Unable to load camera backend '{backend_name}': {exc}")
            print("Falling back to 'picamera'.")
            camera = create_legacy_camera(
                backend_name="picamera",
                rotation=easy_rot,
                preview_res=(VID_WIDTH, VID_HEIGHT),
                device_index=camera_device_index,
            )
        else:
            # Do not silently fall back for USB errors (e.g. wrong device index).
            raise
    print(f"Camera backend active: {getattr(camera, 'backend_name', 'unknown')}")
    camera.framerate = 32
    supports_crosshair_overlay = bool(getattr(camera, "supports_overlay", True))
    print(
        "Crosshair diagnostic:",
        {
            "camera_type": type(camera).__name__,
            "backend_name": getattr(camera, "backend_name", "unknown"),
            "supports_overlay_attr": getattr(camera, "supports_overlay", None),
            "supports_crosshair_overlay": supports_crosshair_overlay,
            "camera_service_module": getattr(type(camera), "__module__", "unknown"),
        },
    )
    if not supports_crosshair_overlay:
        print("Crosshair overlay is not supported by this camera backend.")
    supports_manual_camera_controls = camera_backend_supports_manual_controls(camera)
    if not supports_manual_camera_controls:
        print("Exposure and white-balance controls are not supported by this camera backend.")
    # MHT: 270
    # camera.rotation = 270

    # Cell Sensor, at home, 90
    # camera.rotation = 90
    
    # MHT: 270, Cell Sensor: 90
    # camera.rotation = C.CAMERA_ROTATION_ANGLE
    # Lab stuff
    camera.rotation = easy_rot
    
    # Set Camera Settings:
    # Set Exposure mode
    # camera.exposure_mode = 'fireworks'
    
    # Set AWB Mode
    # camera.awb_mode = 'tungsten'
    
    # Let camera settings settle (bounded wait for backend portability).
    settle_camera_gain(camera)
    
    
    # rawCapture = PiRGBArray(camera, size=(VID_WIDTH, VID_HEIGHT))
    
    #
    # allow the camera to warmup
    time.sleep(0.1)
    
    # Setup 3D Printer
    csv_filename = "testing/file2.csv"
    path_list = printer.get_path_list_csv(csv_filename)
    printer.initial_setup(path_list)
    
    
    # Move Extruder Out Of The Way
    x_start = 0
    y_start = C.Y_MAX
    z_start = 50
    # printer.move_extruder_out_of_the_way(x_start, y_start, z_start)
    
    # Create Temp file to store locations into

    if not os.path.isdir(TEMP_FOLDER):
        os.makedirs(TEMP_FOLDER, exist_ok=True)
        print(f"Folder does not exist, making directory: {TEMP_FOLDER}")

    # Make newline be blank, prevents extra empty lines from happening
    with open(TEMP_FULL_PATH, 'w', newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["X", "Y", "Z"])
    
    # === Camera Preview Startup ===
    global PREVIOUS_CAMERA_PREVIEW_X, PREVIOUS_CAMERA_PREVIEW_Y
    global PREVIEW_LOC_X, PREVIEW_LOC_Y, PREVIEW_WIDTH, PREVIEW_HEIGHT, PREVIEW_ALPHA
    # Initialize preview_win_id to store it when GUI is up.
    preview_win_id = 0
    
    # Initialize is_initial_startup flag as True
    is_initial_startup = True
    
    # Preview Window Creation and Tracking
    # Get random/unique x/y window starting position (top-left)
    # loc_x_list, loc_y_list = get_xy_loc_of_all_windows()
    x_start, y_start = get_unique_xy_loc()
    print(f"x_start: {x_start}")
    print(f"y_start: {y_start}")
    # ===  
    
    sg.theme("LightGreen")

    # Create tabs layout:
    # Tab 1: Start Experiment (Pic, vid, or Preview), Open CSV File. Disable Start Experiment if no CSV loaded
    # Tab 2: Movement Tab, with input GCODE (temp), Future: Move specific coordinates
    #
    
    # Tab 1: Start Experiment Tab
    # TODO: Create 3 Radio Buttons for Picture, Video, Preview (Default), and Prompt "Choose to take Pictures, Video, or only preview locations"
    # TODO: Create User Input for number of Trials (use placeholder)
    time_layout = ET.get_time_layout()
    tab_1_layout = [
        [sg.Text(OPEN_CSV_PROMPT),
         sg.Input(default_text=os.path.join(os.getcwd(), "testing", "Well_Location", "snake_path.csv"),
                  key=OPEN_CSV_FILEBROWSE_KEY, size=(45,1)),
         sg.FileBrowse(initial_folder=os.path.join(os.getcwd(),"testing","Well_Location"),
                       target=OPEN_CSV_FILEBROWSE_KEY)],
        *time_layout,
        [sg.Text(EXP_RADIO_PROMPT)],
        [sg.Radio(EXP_RADIO_PIC_TEXT, EXP_RADIO_GROUP, default=True, key=EXP_RADIO_PIC_KEY),
         sg.Radio(EXP_RADIO_VID_TEXT, EXP_RADIO_GROUP, default=False, key=EXP_RADIO_VID_KEY),
         sg.Radio(EXP_RADIO_PREVIEW_TEXT, EXP_RADIO_GROUP, default=False, key=EXP_RADIO_PREVIEW_KEY)],
        [sg.Text("Save Images to Folder:"),
         sg.In(default_text=PIC_SAVE_FOLDER, size=(25, 1), enable_events=True, key=PIC_SAVE_FOLDER_KEY),
         sg.FolderBrowse(initial_folder=PIC_SAVE_FOLDER)],
        [sg.Button(START_EXPERIMENT, disabled=True), sg.Button(PAUSE_EXPERIMENT, disabled=True),
         sg.Button(RESUME_EXPERIMENT, disabled=True), sg.Button(STOP_EXPERIMENT, disabled=True)]
    ]
    
    # Tab 2: Movement Tab + Crosshair overlay + Corner capture
    crosshair_layout = [
        [sg.Checkbox("Show Crosshair Overlay", key="--XHAIR_ON--", default=supports_crosshair_overlay, disabled=(not supports_crosshair_overlay))],
        [sg.Button("-1", key="--XHAIR_DEC--", size=(4, 1), disabled=(not supports_crosshair_overlay)),
         sg.Text("Radius (px):"),
         sg.InputText("100", size=(5, 1), key="--XHAIR_RADIUS--", enable_events=True, disabled=(not supports_crosshair_overlay)),
         sg.Button("+1", key="--XHAIR_INC--", size=(4, 1), disabled=(not supports_crosshair_overlay))]
    ]
    if not supports_crosshair_overlay:
        crosshair_layout.append([sg.Text("Overlay unavailable on this backend.")])

    corner_layout = [
        [sg.Text("Rows/Cols:"), sg.Input("6", size=(4,1), key="--NUM_ROWS--"), sg.Input("8", size=(4,1), key="--NUM_COLS--"),
         sg.Text("Z Override:"), sg.Input("", size=(6,1), key="--Z_OVERRIDE--"), sg.Button("Apply Z to CSV", key="--APPLY_Z--")],
        [sg.Text("Top-Left:"), sg.Input("", size=(20,1), key="--TL_COORD--"), sg.Button("Set TL", key="--SET_TL--")],
        [sg.Text("Top-Right:"), sg.Input("", size=(20,1), key="--TR_COORD--"), sg.Button("Set TR", key="--SET_TR--")],
        [sg.Text("Bottom-Left:"), sg.Input("", size=(20,1), key="--BL_COORD--"), sg.Button("Set BL", key="--SET_BL--")],
        [sg.Text("Bottom-Right:"), sg.Input("", size=(20,1), key="--BR_COORD--"), sg.Button("Set BR", key="--SET_BR--")],
        [sg.Button("Generate Snake CSV", key="--GEN_SNAKE--")]
    ]

    tab_2_layout = [ [sg.Text("", size=(3, 1)), sg.Button("Get Current Location", size=(20, 1)), sg.Button("Change Plate", key="--CHANGE_PLATE--", size=(12,1)), sg.Button(SAVE_LOC_BUTTON)],
                     [sg.Radio(RELATIVE_TENTH_TEXT, RADIO_GROUP, default=False, key=RELATIVE_TENTH_KEY),
                        sg.Radio(RELATIVE_ONE_TEXT, RADIO_GROUP, default=True, key=RELATIVE_ONE_KEY),
                        sg.Radio(RELATIVE_TEN_TEXT, RADIO_GROUP, default=False, key=RELATIVE_TEN_KEY)
                     ],
                     [sg.Text("", size=(5, 1)), sg.Button(Y_PLUS, size=(10, 1)), sg.Text("", size=(5, 1)), sg.Button(Z_MINUS, size=(5, 1))],
                     [sg.Button(X_MINUS, size=(10, 1)), sg.Button(X_PLUS, size=(10, 1))],
                     [sg.Text("", size=(5, 1)), sg.Button(Y_MINUS, size=(10, 1)), sg.Text("", size=(5, 1)), sg.Button(Z_PLUS, size=(5, 1))],
                     [sg.Text("Input GCODE (e.g. G0X0Y50):")],
                     [sg.InputText(size=(30, 1), key="-GCODE_INPUT-"), sg.Button("Run", size=(5, 1)), sg.Button("Clear", size=(5, 1))],
                     [sg.HorizontalSeparator()],
                     [sg.Frame("Crosshair", crosshair_layout)],
                     [sg.Frame("Corners (csv coords)", corner_layout)]
                   ]
    
    # Setup Tab/GUI Layout
    tab_3_layout = [
        [sg.Text("Camera Rotation (in Degrees):"), sg.InputText("180", size=(10, 1), enable_events=True, key=CAMERA_ROTATION_KEY)],
        [sg.Text("Set Image Capture Resolution:")],
        [sg.Text("Pic Width (in pixels):"), sg.InputText(PIC_WIDTH, size=(10, 1), enable_events=True, key=PIC_WIDTH_KEY)],
        [sg.Text("Pic Height (in pixels):"), sg.InputText(PIC_HEIGHT, size=(10, 1), enable_events=True, key=PIC_HEIGHT_KEY)],
        [sg.Button(UPDATE_CAMERA_TEXT)],
        [sg.HorizontalSeparator()],
        [sg.Text("Camera Settle Time (sec):"), sg.InputText(EXPO_SETTLE_TIME, size=(5, 1), key=EXPO_SETTLE_TIME_KEY)],
        [sg.Frame("Exposure", [
            [sg.Radio("Auto Exposure", EXPOSURE_MODE_GROUP, default=True, key=EXPOSURE_AUTO_KEY, enable_events=True, disabled=(not supports_manual_camera_controls)),
             sg.Radio("Manual Exposure", EXPOSURE_MODE_GROUP, default=False, key=EXPOSURE_MANUAL_KEY, enable_events=True, disabled=(not supports_manual_camera_controls))],
            [sg.Text("Manual Shutter (ms):"), sg.InputText("", size=(8, 1), enable_events=True, key=MANUAL_SHUTTER_MS_KEY, disabled=True),
             sg.Button(APPLY_EXPOSURE_BUTTON, disabled=(not supports_manual_camera_controls))],
            [sg.Text("Current shutter: unavailable", key=EXPOSURE_STATUS_KEY, size=(35, 1))]
        ])],
        [sg.Frame("White Balance", [
            [sg.Button(USE_AUTO_WB_BUTTON, disabled=(not supports_manual_camera_controls)),
             sg.Button(AUTO_WB_LOCK_BUTTON, disabled=(not supports_manual_camera_controls))],
            [sg.Text("Locked Red Gain: --", key=WB_RED_GAIN_STATUS_KEY, size=(25, 1))],
            [sg.Text("Locked Blue Gain: --", key=WB_BLUE_GAIN_STATUS_KEY, size=(25, 1))]
        ])],
        [sg.Text("", key=CAMERA_CONTROL_NOTE_KEY, size=(65, 2))],
        [sg.HorizontalSeparator()],
        [sg.Text("Preview Location (e.g. x = 0, y = 0):")],
        [sg.Text("x:"), sg.InputText("0", size=(8, 1), enable_events=True, key=PREVIEW_LOC_X_KEY),
         sg.Text("y:"), sg.InputText("36", size=(8, 1), enable_events=True, key=PREVIEW_LOC_Y_KEY)],
        [sg.Text("Preview Video Size (e.g. width = 640, height = 480):")],
        [sg.Text("width:"), sg.InputText("640", size=(8, 1), enable_events=True, key=PREVIEW_WIDTH_KEY),
         sg.Text("height:"), sg.InputText("480", size=(8, 1), enable_events=True, key=PREVIEW_HEIGHT_KEY)],
        [sg.Text("Opacity, or Alpha (range 0 (invisible) to 255 (opaque)):"), sg.InputText("255", size=(5, 1), enable_events=True, key=ALPHA_KEY)],
        [sg.Button(START_PREVIEW), sg.Button(STOP_PREVIEW)]
    ]
    
    # Z Stack Tab
    tab_4_layout = [ [sg.Text("Input Z Stack Parameters (Units are in mm):")],
                       [sg.Text("Z Start:"), sg.InputText("0", size=(7, 1), enable_events=True, key=Z_START_KEY),
                        sg.Text("Z End:"),sg.InputText("2", size=(7, 1), enable_events=True, key=Z_END_KEY),
                        sg.Text("Z Inc:"),sg.InputText("0.5", size=(7, 1), enable_events=True, key=Z_INC_KEY)],
                       [sg.Text("Save Folder Location:"), sg.In(size=(25,1), enable_events=True, key=SAVE_FOLDER_KEY), sg.FolderBrowse()],
                       [sg.Button(START_Z_STACK_CREATION_TEXT)]
                   ]
    
    # TABs Layout (New, Experimental
    # TODO: Put in Pic/Video Button, test them out.
    layout = [ [sg.Image(filename='', key='-IMAGE-')],
               [sg.TabGroup([[sg.Tab("Tab 1 (Exp)", tab_1_layout, key="-TAB_1_KEY"),
                              sg.Tab("Tab 2 (Mvmt)", tab_2_layout),
                              sg.Tab("Tab 3 (CAM)", tab_3_layout),
                              sg.Tab("Tab 4 (Z Stack)", tab_4_layout)]])
               ],
               [sg.Button("Pic"), sg.Button("Vid"), sg.Button("Pic x 10")]
             ]
    
    # Setup Camera Preview Pseudo Window
    layout_p = [[sg.Text("Preview Window. Click and Drag me around to move window!", size=(55, 10))]]
    window_p = sg.Window("Camera Preview Pseudo Window", layout_p, grab_anywhere=True, location=(x_start, y_start))
    
    # Define Window Layout (Original)
    # layout = [
        # [sg.Image(filename='', key='-IMAGE-')],
        # [sg.Text("", size=(3, 1)), sg.Button("Get Current Location", size=(20, 1))],
        # [sg.Radio(RELATIVE_TENTH_TEXT, RADIO_GROUP, default=False, key=RELATIVE_TENTH_KEY),
            # sg.Radio(RELATIVE_ONE_TEXT, RADIO_GROUP, default=True, key=RELATIVE_ONE_KEY),
            # sg.Radio(RELATIVE_TEN_TEXT, RADIO_GROUP, default=False, key=RELATIVE_TEN_KEY)],
        # [sg.Text("", size=(5, 1)), sg.Button(Y_PLUS, size=(10, 1)), sg.Text("", size=(5, 1)), sg.Button(Z_MINUS, size=(5, 1))],
        # [sg.Button(X_MINUS, size=(10, 1)), sg.Button(X_PLUS, size=(10, 1))],
        # [sg.Text("", size=(5, 1)), sg.Button(Y_MINUS, size=(10, 1)), sg.Text("", size=(5, 1)), sg.Button(Z_PLUS, size=(5, 1))],
        # [sg.HorizontalSeparator()],
        # [sg.Text("Input GCODE (e.g. G0X0Y50):")],
        # [sg.InputText(size=(30, 1), key="-GCODE_INPUT-"), sg.Button("Run", size=(5, 1)), sg.Button("Clear", size=(5, 1))]
    # ]
    # Have Camera Feed Window
    # To the right, xy, and z
    # Below camera Feed: Show Current Location, Get Current Location Button
    
    # Threading Setup
    # Initialize empty experiment_thread object, will be used with "Start Experiment" is pushed
    experiment_thread = threading.Thread()
    
    # Initialize threading event (Allows you to stop the thread)
    thread_event = threading.Event()
    pause_event = threading.Event()

    crosshair_overlay = None
    corners = {"TL": None, "TR": None, "BL": None, "BR": None}
    last_snake_csv = os.path.join(os.getcwd(), "testing", "Well_Location", "snake_path.csv")

    # Create window and show it without plot
    window = sg.Window("3D Printer GUI Test", layout, location=(640, 36), finalize=True)
    initialize_camera_control_panel(window, camera, supports_manual_camera_controls)
    
    
    # Create experiment_run_counter
    experiment_run_counter = 0
    # Create Boolean is_running_experiment, default False
    is_running_experiment = False
    # Initialize well_counter to 0 (used for running experiment, going through GCode location list)
    
    # Initialize current_location_dictionary to X=0, Y=0, Z=0
    
    # Initialize folder_path_sample to "" ("Start Experiment" will create unique folder name)
    # Throttle preview window polling to reduce CPU use
    preview_check_interval = 0.2
    last_preview_check = time.monotonic()
    # **** Note: This for loop may cause problems if the camera feed dies, it will close everything? ****
    while True:
        event, values = window.read(timeout=20)
        event_p, values_p = window_p.read(timeout=20)
        
        # Camera Preview Initial Startup
        # Setup if/else initial_startup condition
        # If initial startup,
        if is_initial_startup == True:
            # print(f"is_initial_startup: {is_initial_startup}")
            # Get PID of Preview Window
            preview_win_id = get_window_pid(x_start, y_start)
            
            # Change Camera Preview Window Name
            new_window_name = "Camera Preview Window"
            change_window_name(preview_win_id, new_window_name)
            # Move This Window to where I want it (0,0)?
            x_new = 0
            y_new = 36
            move_window_pid(preview_win_id, x_new, y_new)
            
            # Start Camera Too PREVIEW_LOC_X, PREVIEW_LOC_Y, PREVIEW_WIDTH, PREVIEW_HEIGHT, PREVIEW_ALPHA
            camera.start_preview(alpha=PREVIEW_ALPHA, fullscreen=False, window=(PREVIEW_LOC_X, y_new + PREVIEW_WINDOW_OFFSET, PREVIEW_WIDTH, PREVIEW_HEIGHT))
            
            # Change is_initial_startup to False
            is_initial_startup = False
        else:
            now = time.monotonic()
            if now - last_preview_check >= preview_check_interval:
                last_preview_check = now
                x_win_preview, y_win_preview = get_window_location_from_pid(preview_win_id)
                if (PREVIOUS_CAMERA_PREVIEW_X != x_win_preview) or (PREVIOUS_CAMERA_PREVIEW_Y != y_win_preview):
                    PREVIOUS_CAMERA_PREVIEW_X = x_win_preview
                    PREVIOUS_CAMERA_PREVIEW_Y = y_win_preview
                
                    if camera.preview:
                        camera.start_preview(alpha=PREVIEW_ALPHA, fullscreen=False, window=(x_win_preview, y_win_preview + PREVIEW_WINDOW_OFFSET, PREVIEW_WIDTH, PREVIEW_HEIGHT))
                        # If crosshair overlay is on, move it with the preview window
                        if supports_crosshair_overlay and values.get("--XHAIR_ON--", True):
                            try:
                                current_rad = int(values.get("--XHAIR_RADIUS--", WL.CIRCLE_RADIUS))
                            except (TypeError, ValueError):
                                current_rad = WL.CIRCLE_RADIUS
                            if crosshair_overlay:
                                with CAMERA_LOCK:
                                    camera.remove_overlay(crosshair_overlay)
                            preview_rect = (x_win_preview, y_win_preview + PREVIEW_WINDOW_OFFSET, PREVIEW_WIDTH, PREVIEW_HEIGHT)
                            crosshair_overlay = WL.create_crosshair_overlay(
                                camera,
                                radius=current_rad,
                                thickness=WL.CIRCLE_THICKNESS,
                                color_bgr=WL.CIRCLE_COLOR,
                                alpha=PREVIEW_ALPHA,
                                preview_window=preview_rect,
                                camera_lock=CAMERA_LOCK,
                                existing_overlay=None
                            )
        
        # Check Input Text for integers only
        
        for numeric_key in NUMERIC_KEYS:
            check_for_digits_in_key(numeric_key, window, event, values)
        
        # Call Get Current Location Manager Function
        # Print Current Location
        
        # TODO: Create new thread for Current Location display?
        
        # Convert captured frame to array format, then overwrite frame variable (temporary solution)
        # frame = frame.array
        
        # If in experiment mode, resize image if it is larger than when rawCapture was created
        # if is_running_experiment == True:
            # Resize frame to size of window, maybe
            # rawCapture = PiRGBArray(camera, size=(VID_WIDTH, VID_HEIGHT))
            # frame = cv2.resize(frame, (VID_WIDTH, VID_HEIGHT))
        
        # TODO: Add in image resizer if in experiment mode. Temp fix to allow for max image resolution while running experiment.
        
        # If event is not closing, check for CSV file. This is to prevent the closing GUI crash.
        if event != sg.WIN_CLOSED:
            # ---- CSV File Checker and "Start Experiment" Enable/Disable If/Else logic
            # Check if CSV file Exists (length is 0 if CSV not loaded)
            #  Enable "Start Experiment" if true, else disable "Start Experiment"
            if len(values[OPEN_CSV_FILEBROWSE_KEY]) != 0 and is_running_experiment == False:
                # print("CSV File Exists")
                # Enable "Start Experiment" button
                window[START_EXPERIMENT].update(disabled=False)
                # print("values[OPEN_CSV_FILEBROWSE_KEY]:", values[OPEN_CSV_FILEBROWSE_KEY])
                # print(len(values[OPEN_CSV_FILEBROWSE_KEY]))
                # Disable "Stop Experiment" button
                window[STOP_EXPERIMENT].update(disabled=True)
            else:
                # print("CSV File Does Not Exist")
                # Disable "Start Experiment" button
                window[START_EXPERIMENT].update(disabled=True)
        
        # ---- Main GUI Window If/elif chain ----
        if event == sg.WIN_CLOSED:
            break
        # Tab 1 (Experiment):
        elif event == START_EXPERIMENT:
            print("You pressed Start Experiment")

            schedule_errors = ET.validate_round_settings(values)
            if schedule_errors:
                print("Cannot start experiment:")
                for error in schedule_errors:
                    print(f"- {error}")
                continue
            
            # Set is_running_experiment to True, we are now running an experiment
            is_running_experiment = True
            thread_event.clear()
            pause_event.clear()
            
            # Uncomment to see your CSV File (is it the correct path?)
            # print("CSV File:", values[OPEN_CSV_FILEBROWSE_KEY])
            
            # Disable "Start Experiment" Button
            window[START_EXPERIMENT].update(disabled=True)
            # Enable "Stop Experiment" Button
            window[STOP_EXPERIMENT].update(disabled=False)
            window[PAUSE_EXPERIMENT].update(disabled=False)
            window[RESUME_EXPERIMENT].update(disabled=True)
            
            # Create actual experiment_thread
            experiment_thread = threading.Thread(
                target=run_experiment2,
                args=(event, values, thread_event, pause_event, camera, preview_win_id),
                daemon=True
            )
            experiment_thread.start()
            
            # Create Unique Folder, Get that Unique Folder's Name
            
            # Non-Thread Version of Running Experiment
            # run_experiment_gui(values, camera)
            
        elif event == STOP_EXPERIMENT:
            print("You pressed Stop Experiment")
            print("Ending experiment after current run")
            experiment_run_counter = 0
            is_running_experiment = False
            # Enable "Start Experiment" Button
            window[START_EXPERIMENT].update(disabled=False)
            # Disable "Stop Experiment" Button
            window[STOP_EXPERIMENT].update(disabled=True)
            window[PAUSE_EXPERIMENT].update(disabled=True)
            window[RESUME_EXPERIMENT].update(disabled=True)
            
            # Stop thread, set prepares stopping
            thread_event.set()
            pause_event.clear()
            
            # Stop experiemnt_thread
            experiment_thread.join(timeout=1)
        
        elif event == PAUSE_EXPERIMENT:
            print("You pressed Pause Experiment")
            pause_event.set()
            window[PAUSE_EXPERIMENT].update(disabled=True)
            window[RESUME_EXPERIMENT].update(disabled=False)
        
        elif event == RESUME_EXPERIMENT:
            print("You pressed Resume Experiment")
            pause_event.clear()
            window[PAUSE_EXPERIMENT].update(disabled=False)
            window[RESUME_EXPERIMENT].update(disabled=True)
            
        elif event == "Pic":
            print("You Pushed Pic Button")
            get_picture(camera)
        elif event == "Pic x 10":
            print("Pic x 10")
            x = 10
            delay_seconds = 5
            get_x_pictures(x, delay_seconds, camera)
            
        elif event == "Vid":
            print("You Pushed Vid Button")
            # Take a Video
            get_video(camera)
            
        # Tab 2 (Movement)
        elif event == "Get Current Location":
            print("===================================")
            print("You pressed Get Current Location!")
            get_current_location2()
        elif event in [X_PLUS, X_MINUS, Y_PLUS, Y_MINUS, Z_PLUS, Z_MINUS]:
            # If any of the direction buttons are pressed, move extruder
            #  in that direction using the increment radio amounts
            run_relative(event, values)
        elif event == "Run":
            # Run GCODE found in the GCode  InputText box
            printer.run_gcode(values["-GCODE_INPUT-"])
        elif event == "Clear":
            # Clear GCode InputText box
            window.FindElement("-GCODE_INPUT-").Update("")
        elif event == UPDATE_CAMERA_TEXT:
            # TAB 3 elif statements
            print("Updating Camera Settings...")
            
            # Update Camera Rotation Angle
            camera_rotation_value = values[CAMERA_ROTATION_KEY]
            camera_rotation_angle = int(camera_rotation_value)
            
            #print(f"Cam Rotation: {camera_rotation_angle}")
            camera.rotation = camera_rotation_angle
            
            # Update Still Image Capture Resolution:
            # global PIC_WIDTH, PIC_HEIGHT
            
            new_pic_width = int(values[PIC_WIDTH_KEY])
            new_pic_height = int(values[PIC_HEIGHT_KEY])
            print(f"New Still Image Resolution: {new_pic_width, new_pic_height}")
            PIC_WIDTH = new_pic_width
            PIC_HEIGHT = new_pic_height
            #print(f"Global: {PIC_WIDTH, PIC_HEIGHT}")
        elif event in [EXPOSURE_AUTO_KEY, EXPOSURE_MANUAL_KEY]:
            update_camera_control_enabled_state(
                window,
                supports_manual_camera_controls,
                bool(values.get(EXPOSURE_MANUAL_KEY, False))
            )
        elif event == APPLY_EXPOSURE_BUTTON:
            apply_exposure_settings(values, window, camera, supports_manual_camera_controls)
        elif event == USE_AUTO_WB_BUTTON:
            enable_auto_white_balance(camera, supports_manual_camera_controls)
        elif event == AUTO_WB_LOCK_BUTTON:
            lock_auto_white_balance(values, window, camera, supports_manual_camera_controls)
        elif event == START_Z_STACK_CREATION_TEXT:
            print(f"You pressed button: {START_Z_STACK_CREATION_TEXT}")
            z_start = float(values[Z_START_KEY])
            z_end = float(values[Z_END_KEY])
            z_inc = float(values[Z_INC_KEY])
            
            # If nothing chosen, use default folder location:
            if len(values[SAVE_FOLDER_KEY]) == 0:
                save_folder_location = PIC_SAVE_FOLDER
            else:
                save_folder_location = values[SAVE_FOLDER_KEY]
            print(f"save_folder_location: {save_folder_location}")
            create_z_stack(z_start, z_end, z_inc, save_folder_location, camera)
        elif event == SAVE_LOC_BUTTON:
            print(f"You pressed: {SAVE_LOC_BUTTON}")
            save_current_location()
        elif event == "--CHANGE_PLATE--":
            # Move plate forward in Y to clear space for swapping
            try:
                target_y = 230
                printer.run_gcode(f"G90")
                printer.run_gcode(f"G0Y{target_y}")
                print(f"Moved plate to Y={target_y} for plate change.")
            except Exception as e:
                print(f"Failed to move for plate change: {e}")
        # Corner capture buttons
        elif event in ["--SET_TL--", "--SET_TR--", "--SET_BL--", "--SET_BR--"]:
            loc = get_current_location2()
            coord_str = f"{loc['X']:.2f},{loc['Y']:.2f},{loc['Z']:.2f}"
            if event == "--SET_TL--":
                corners["TL"] = loc
                window["--TL_COORD--"].update(coord_str)
            elif event == "--SET_TR--":
                corners["TR"] = loc
                window["--TR_COORD--"].update(coord_str)
            elif event == "--SET_BL--":
                corners["BL"] = loc
                window["--BL_COORD--"].update(coord_str)
            elif event == "--SET_BR--":
                corners["BR"] = loc
                window["--BR_COORD--"].update(coord_str)
        elif event == "--GEN_SNAKE--":
            try:
                rows = int(values.get("--NUM_ROWS--", "0"))
                cols = int(values.get("--NUM_COLS--", "0"))
            except ValueError:
                print("Rows/Cols must be integers")
                continue
            missing = [k for k,v in corners.items() if v is None]
            if missing:
                print(f"Missing corners: {missing}")
                continue
            z_override = None
            z_str = values.get("--Z_OVERRIDE--", "").strip()
            if len(z_str):
                try:
                    z_override = float(z_str)
                except ValueError:
                    print("Z Override must be a number")
                    continue
            default_dir = os.path.join(os.getcwd(), "testing", "Well_Location")
            outfile = os.path.join(default_dir, "snake_path.csv")
            generate_snake_csv(corners, rows, cols, outfile, z_override=z_override)
            last_snake_csv = outfile
            print(f"Snake path saved to {outfile}")
        elif event == "--APPLY_Z--":
            z_str = values.get("--Z_OVERRIDE--", "").strip()
            if not len(z_str):
                print("Enter a Z Override value first")
                continue
            try:
                z_override = float(z_str)
            except ValueError:
                print("Z Override must be a number")
                continue
            # Rewrite last_snake_csv with new Z
            if not os.path.isfile(last_snake_csv):
                print("No snake_path.csv found yet; generate first.")
                continue
            # Reload corners/rows/cols from existing file length
            with open(last_snake_csv, newline="") as f:
                reader = csv.reader(f)
                rows_list = list(reader)
            if len(rows_list) < 2:
                print("Existing snake file is empty.")
                continue
            total_points = len(rows_list) - 1
            # Determine rows/cols from inputs or infer nothing; just rewrite Z
            # Simply rewrite the file with same XY, new Z
            with open(last_snake_csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["image#", "Xcoord", "Ycoord", "Zcoord"])
                for row in rows_list[1:]:
                    if len(row) < 4:
                        continue
                    writer.writerow([row[0], row[1], row[2], f"{z_override:.2f}"])
            print(f"Updated Z to {z_override:.2f} in {last_snake_csv}")
        elif event == START_PREVIEW:
            print("Starting Preview With Settings")
            if camera.preview:
                camera.stop_preview()
            try:
                prev_width = int(values[PREVIEW_WIDTH_KEY])
                prev_height = int(values[PREVIEW_HEIGHT_KEY])
                prev_loc_x = int(values[PREVIEW_LOC_X_KEY])
                prev_loc_y = int(values[PREVIEW_LOC_Y_KEY])
                alpha_val = int(values[ALPHA_KEY])
            except (TypeError, ValueError):
                print("Invalid preview settings")
            else:
                PREVIEW_LOC_X = prev_loc_x
                PREVIEW_LOC_Y = prev_loc_y
                PREVIEW_WIDTH = prev_width
                PREVIEW_HEIGHT = prev_height
                PREVIEW_ALPHA = alpha_val
                move_window_pid(preview_win_id, prev_loc_x, prev_loc_y - PREVIEW_WINDOW_OFFSET)
                camera.start_preview(alpha=alpha_val, fullscreen=False, window=(prev_loc_x, prev_loc_y, prev_width, prev_height))
                x_win, y_win = get_window_location_from_pid(preview_win_id)
                print(f"x_win:{x_win}, y_win:{y_win}")
        elif event == STOP_PREVIEW:
            print("Stopping Preview")
            camera.stop_preview()
        if event == PIC_SAVE_FOLDER_KEY:
            save_folder = values[PIC_SAVE_FOLDER_KEY]
            print(f"Save folder: {save_folder}")
            
            PIC_SAVE_FOLDER = save_folder

        
        # Crosshair controls (Movement tab)
        if event in ["--XHAIR_INC--", "--XHAIR_DEC--", "--XHAIR_RADIUS--"]:
            try:
                current_rad = int(values.get("--XHAIR_RADIUS--", WL.CIRCLE_RADIUS))
            except (TypeError, ValueError):
                current_rad = WL.CIRCLE_RADIUS
            if event == "--XHAIR_INC--":
                current_rad += 1
            elif event == "--XHAIR_DEC--":
                current_rad = max(1, current_rad - 1)
            WL.CIRCLE_RADIUS = current_rad
            window["--XHAIR_RADIUS--"].update(str(current_rad))
            values["--XHAIR_RADIUS--"] = str(current_rad)
            if supports_crosshair_overlay and values.get("--XHAIR_ON--", True):
                # Update overlay on preview
                x_win_preview, y_win_preview = get_window_location_from_pid(preview_win_id)
                preview_rect = (x_win_preview, y_win_preview + PREVIEW_WINDOW_OFFSET, PREVIEW_WIDTH, PREVIEW_HEIGHT)
                crosshair_overlay = WL.create_crosshair_overlay(
                    camera,
                    radius=current_rad,
                    thickness=WL.CIRCLE_THICKNESS,
                    color_bgr=WL.CIRCLE_COLOR,
                    alpha=PREVIEW_ALPHA,
                    preview_window=preview_rect,
                    camera_lock=CAMERA_LOCK,
                    existing_overlay=crosshair_overlay
                )
            else:
                if crosshair_overlay:
                    with CAMERA_LOCK:
                        camera.remove_overlay(crosshair_overlay)
                    crosshair_overlay = None
        # Well location calculator tab events
        if event in WLC.WELL_LOCATION_EVENTS or event in [WLC.ROW_KEY, WLC.COL_KEY, WLC.SAVE_FOLDER_KEY]:
            WLC.event_manager(event, values, window)
        elif event == "--XHAIR_ON--":
            if not supports_crosshair_overlay:
                window["--XHAIR_ON--"].update(value=False)
                crosshair_overlay = None
            elif values.get("--XHAIR_ON--", True):
                try:
                    current_rad = int(values.get("--XHAIR_RADIUS--", WL.CIRCLE_RADIUS))
                except (TypeError, ValueError):
                    current_rad = WL.CIRCLE_RADIUS
                x_win_preview, y_win_preview = get_window_location_from_pid(preview_win_id)
                preview_rect = (x_win_preview, y_win_preview + PREVIEW_WINDOW_OFFSET, PREVIEW_WIDTH, PREVIEW_HEIGHT)
                crosshair_overlay = WL.create_crosshair_overlay(
                    camera,
                    radius=current_rad,
                    thickness=WL.CIRCLE_THICKNESS,
                    color_bgr=WL.CIRCLE_COLOR,
                    alpha=PREVIEW_ALPHA,
                    preview_window=preview_rect,
                    camera_lock=CAMERA_LOCK,
                    existing_overlay=crosshair_overlay
                )
            else:
                if crosshair_overlay:
                    with CAMERA_LOCK:
                        camera.remove_overlay(crosshair_overlay)
                    crosshair_overlay = None
        
        # print("You entered ", values[0])
        
        # Original
        # imgbytes = cv2.imencode('.png', frame)[1].tobytes()
        
        # Update GUI Window with new image
        # window['-IMAGE-'].update(data=imgbytes)
        
        # clear the stream in preparation for the next frame
        # Must do this, else it won't work
        # rawCapture.truncate(0)

    # Out of While Loop
    camera.stop_preview()
    camera.close()
    
    # Closing Window
    window.close()
    
    # Closing 3D Printer Serial Connection
    printer.printer.close()
    
    # For loop to show camera feed
    pass

main()
# call main function
