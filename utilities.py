import subprocess
import platform
import json
import global_var
import cv2
import platform

def open_onscreen_keyboard():
    system = platform.system()

    try:
        if system == "Windows":
            subprocess.run('start osk', shell=True)
        elif system == "Darwin":
            import keyboard as k
            k.main()
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

def get_available_cameras(max_test=5):
    cameras = []
    current_index = get_camera_input()

    for i in range(max_test):
        cap = cv2.VideoCapture(i)

        if not cap.isOpened():
            cap.release()
            break

        cameras.append({
            "name": f"Camera {i}",
            "index": i
        })

        cap.release()

    if current_index is not None and all(c["index"] != current_index for c in cameras):
        cameras.append({
            "name": f"Camera {current_index} (Unavailable)",
            "index": current_index
        })

    return cameras


def set_camera_input(value):
    global_var.camera_input_changed = True

    try:
        with open(".vscode/settings.json", "r") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}

    settings["camera_input"] = value

    with open(".vscode/settings.json", "w") as f:
        json.dump(settings, f, indent=4)
    
    
    print(f"Saved Camera Index: {value}")

def get_camera_input():
    try:
        with open(".vscode/settings.json", "r") as f:
            data = json.load(f)
        return data.get("camera_input")
    except:
        return 0

if __name__ == "__main__":
    open_onscreen_keyboard()
    set_camera_input(1)
    print(global_var.camera_input_changed)

