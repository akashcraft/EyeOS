import subprocess
import platform
import os
import keyboard as k

def open_onscreen_keyboard():
    system = platform.system()

    try:
        if system == "Windows":
            subprocess.run('start osk', shell=True)
        elif system == "Darwin":
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

if __name__ == "__main__":
    open_onscreen_keyboard()
