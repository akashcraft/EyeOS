
import json
import os

def save_calibration(data, filename="calibration.json"):
    with open(filename, "w") as f:
        json.dump(data, f)
    print(f"Saved calibration to {filename}")

def load_calibration(filename="calibration.json"):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            data = json.load(f)
        print(f"Loaded calibration from {filename}")
        return data
    return None
