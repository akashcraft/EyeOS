import subprocess
import platform
import json
import global_var
import os
import cv2
import re


def open_onscreen_keyboard():
    system = platform.system()

    try:
        if system == "Windows":
            subprocess.run('start osk', shell=True)
        elif system == "Darwin":
            # macOS
            subprocess.run([
                "osascript", "-e",
                'tell application "System Events" to key code 28 using {command down, option down}'
            ])
        elif system == "Linux":
            if subprocess.call(["which", "onboard"], stdout=subprocess.DEVNULL) == 0:
                subprocess.Popen(["onboard"])
            elif subprocess.call(["which", "florence"], stdout=subprocess.DEVNULL) == 0:
                subprocess.Popen(["florence"])
            else:
                print("No on-screen keyboard found. Install with: sudo apt install onboard")
        else:
            print(f"Unsupported OS: {system}")

    except Exception as e:
        print(f"Failed to open on-screen keyboard: {e}")

def set_camera_input(value):
    """
    Sets the global variable camera_input_changed to True,
    and updates 'camera_input' in settings.json with the given numeric value.
    """
    
    global_var.camera_input_changed = True

    # Validate the input
    if not isinstance(value, (int, float)):
        raise ValueError("camera_input must be a number")

    # Try loading existing settings
    try:
        with open(".vscode\settings.json", "r") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}

    # Update the camera_input value
    settings["camera_input"] = value

    # Save back to file
    with open(".vscode\settings.json", "w") as f:
        json.dump(settings, f, indent=4)

    print(f"Camera input set to {value}. Global flag set to True.")


def get_camera_input():
    with open(".vscode\settings.json", "r") as f:
        data = json.load(f)
    return data.get("camera_input")

if __name__ == "__main__":
    open_onscreen_keyboard()
    set_camera_input(1)
    print(global_var.camera_input_changed)  # True
