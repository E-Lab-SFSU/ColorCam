"""
Module for configuring how many experiment rounds to run.

Each round is one full pass through the loaded well list. The user also
provides the interval to wait between completed rounds.
"""

import FreeSimpleGUI as sg
import time

DEFAULT_ROUND_COUNT = "1"
DEFAULT_ROUND_INTERVAL_MIN = "1"

ROUND_COUNT_KEY = "-ROUND_COUNT-"
ROUND_INTERVAL_MIN_KEY = "-ROUND_INTERVAL_MIN-"

ROUND_INPUT_KEY_LIST = [ROUND_COUNT_KEY, ROUND_INTERVAL_MIN_KEY]


# Define function to check an InputText key for digits only
def check_for_digits_in_key(key_str, window, event, values):
    
    # TODO: Add in character check in all of number string.
    if event == key_str and len(values[key_str]) and values[key_str][-1] not in ('0123456789'):
            # delete last char from input
            # print("Found a letter instead of a number")
            window[key_str].update(values[key_str][:-1])


def get_time_layout():
    input_size = (5, 1)
    
    time_layout = [
                    [sg.Text("How many rounds of photos should I collect?")],
                    [sg.Text("Rounds:"), sg.InputText(DEFAULT_ROUND_COUNT, size=input_size, enable_events=True, key=ROUND_COUNT_KEY)],
                    [sg.Text("How long should I wait between rounds?")],
                    [sg.Text("Min(s):"), sg.InputText(DEFAULT_ROUND_INTERVAL_MIN, size=input_size, enable_events=True, key=ROUND_INTERVAL_MIN_KEY)]
                  ]
    return time_layout


def validate_round_settings(values):
    errors = []

    round_count_text = str(values.get(ROUND_COUNT_KEY, "")).strip()
    interval_text = str(values.get(ROUND_INTERVAL_MIN_KEY, "")).strip()

    if len(round_count_text) == 0:
        errors.append("Enter the number of rounds.")
    elif int(round_count_text) < 1:
        errors.append("Number of rounds must be at least 1.")

    if len(interval_text) == 0:
        errors.append("Enter the interval between rounds.")
    elif int(interval_text) < 0:
        errors.append("Interval between rounds must be 0 minutes or greater.")

    return errors


def get_round_settings(values):
    errors = validate_round_settings(values)
    if errors:
        raise ValueError("; ".join(errors))

    round_count = int(values[ROUND_COUNT_KEY])
    interval_minutes = int(values[ROUND_INTERVAL_MIN_KEY])
    interval_seconds = interval_minutes * 60

    print(f"Experiment will run for {round_count} round(s)")
    print(
        f"Between completed rounds, will wait {interval_minutes} minute(s) "
        f"(or {interval_seconds} second(s)) before collecting data again"
    )

    return round_count, interval_seconds


def demo_start_experiment_1(round_count, interval_seconds):
    print("demo_start_experiment_1")

    location_list = [1, 2, 3, 4]

    for round_index in range(round_count):
        print(f"Round #{round_index + 1}")
        for loc in location_list:
            print(loc)
            time.sleep(1)

        if round_index < (round_count - 1):
            print(f"Will wait {interval_seconds} seconds until collecting data again")
            time.sleep(interval_seconds)

    print("Done running experiment")


def demo_start_experiment_2(round_count, interval_seconds):
    print("demo_start_experiment_2")

    location_list = [1, 2, 3, 4]

    for round_index in range(round_count):
        print(f"Round #{round_index + 1}")
        for loc in location_list:
            print(loc)
            time.sleep(1)
        if round_index < (round_count - 1):
            print(f"Will wait {interval_seconds} sec before doing next round.")
            wait_start = time.monotonic()
            while (time.monotonic() - wait_start) < interval_seconds:
                time.sleep(0.25)

    print("Done running experiment")


def demo_time_left():
    # Temp function for displaying time left every x seconds

    # Init start time
    start_time = time.monotonic()

    elapsed_time = 0

    total_seconds = 61  # sec
    # total_seconds = 3661  # sec

    when_to_display_time_left = 5   # sec

    # While loop that lasts for 30 seconds
    while elapsed_time < total_seconds:
        #  Get current time
        current_time = time.monotonic()

        #  Calculate elapsed time
        elapsed_time = current_time - start_time

        #  Calc time left
        time_left = total_seconds - elapsed_time
        # print(f"elapsed_time: {elapsed_time}")

        #  Convert time left to int, if mod 5 is 0, display time
        time_left_sec_int = int(time_left)
        time_left_min = time_left/60
        time_left_min_int = int(time_left_min)
        time_left_hours = time_left/(60*60)

        if (time_left_sec_int % when_to_display_time_left) == 0:
            #  every 5 seconds, display time left

            # TODO: Display hours and minutes left if minutes > 60
            if time_left_sec_int >= 60*60:
                # print(f"Hours left: {time_left_hours}")
                hours_left = int(time_left_hours)
                minutes_left = (time_left_hours % hours_left) * 60
                minutes_left_int = int(minutes_left)
                if minutes_left_int != 0:
                    seconds_left = int((minutes_left % minutes_left_int) * 60)
                    print(f"time left: {hours_left} hour(s), {minutes_left_int} minute(s), and {seconds_left} second(s).")
                else:
                    seconds_left = int(minutes_left * 60)
                    print(f"time left: {hours_left} hour(s), {seconds_left} second(s).")
                    # print(f"minutes_left: {minutes_left}")
                # print(f"After decimal: {time_left_min % time_left_min_int}")
                # print(f"time_left: {time_left_min} minutes")
                # print(f"time_left: {minutes_left} minutes and {seconds_left} seconds")
                # print(f"time left: {hours_left} hour(s) and {minutes_left_int} minute(s).")

            # TODO: Display minutes left if seconds > 60.
            elif time_left_sec_int > 60:
                minutes_left = int(time_left_min)
                seconds_left = int((time_left_min % time_left_min_int) * 60)
                # print(f"After decimal: {time_left_min % time_left_min_int}")
                # print(f"time_left: {time_left_min} minutes")
                print(f"time_left: {minutes_left} minutes and {seconds_left} seconds")

            # Display seconds left if 60 seconds are left
            elif time_left_sec_int <= 60:
                print(f"time_left: {time_left_sec_int} second(s)")

            # print(f"time_left: {time_left_sec_int} seconds")
            # Figure out way to remove sleep
            time.sleep(1)

            # Since sleeping for 1 second, update current and elapsed time.
            current_time = time.monotonic()
            elapsed_time = current_time - start_time
            # print(f"elapsed_time: {elapsed_time:.2f} sec")
    print("Out of while loop")





    pass


def main2():
    demo_time_left()


def main():
    print("main")
    
    # Set up theme
    sg.theme("LightGreen")
    
    time_size = (3, 1)
    
    # Set up layout
    layout = [
                *get_time_layout(),
                [sg.Button("Start")]
             ]
    
    # Set up window
    window = sg.Window("Time GUI", layout)
    
    # While loop for GUI
    while True:
        event, values = window.read()
        
        for time_key in ROUND_INPUT_KEY_LIST:
            check_for_digits_in_key(time_key, window, event, values)
        
        if event == sg.WIN_CLOSED:
            break
        elif event == "Start":
            print("Pressed Start")
            errors = validate_round_settings(values)
            if errors:
                for error in errors:
                    print(error)
                continue
            get_round_settings(values)
    
    pass


if __name__ == "__main__":
    main()
    # main2()
