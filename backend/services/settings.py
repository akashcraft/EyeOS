'''
This file is used to manage settings in the EyeOS application.

Functions include:
    create_settings()
    read_settings()
    write_settings()
    reset_demo()
    check_resource()
    _load_settings_dict()
    _atomic_write_json()
    export_settings()
    import_settings()
'''

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

def create_settings(setting_name, setting_value,
                    settings_file='settings.json',
                    default_settings_file = 'default_settings.json'):
    '''
    This function is used to add new settings to the settings and default_settings json files to be used later
    '''

    def update_file(file_path):
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}
        else:
            data = {}

        data[setting_name] = setting_value

        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)

    update_file(settings_file)
    update_file(default_settings_file)

def read_settings(setting_name, settings_file='settings.json', default=None):
    '''
    This is used to read setting values in only the current settings file
    '''
    if not os.path.exists(settings_file):
        return default

    with open(settings_file, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return default

    return data.get(setting_name)

def write_settings(setting_name, setting_value, setting_file='settings.json'):
    '''
    This is used to write setting values in only the current settings file
    '''
    if not os.path.exists(setting_file):
        return
    
    with open(setting_file, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return  

    if setting_name not in data:
        return  

    data[setting_name] = setting_value

    with open(setting_file, 'w') as f:
        json.dump(data, f, indent=4)

def reset_demo(settings_file='settings.json', default_settings_file='default_settings.json'):
    '''
    Used to reset the settings to a based default state.
    '''
    if not os.path.exists(default_settings_file):
        raise FileNotFoundError(f"Default settings file not found: {default_settings_file}")

    with open(default_settings_file, 'r') as src:
        try:
            default_data = json.load(src)
        except json.JSONDecodeError:
            raise ValueError(f"Default settings file is not valid JSON: {default_settings_file}")

        with open(settings_file, 'w') as dst:
            json.dump(default_data, dst, indent=4)

    
def _load_settings_dict(settings_file: str | os.PathLike = "settings.json") -> dict:

    '''
    loads the entire settings JSON file into a dictionary, raising clear errors if the file is missing or invalid
    '''
    
    p = Path(settings_file)
    if not p.exists():
        raise FileNotFoundError(f"Settings file not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Settings file is not valid JSON: {p}") from e

    
def _atomic_write_json(obj: dict, dest: Path, pretty: bool) -> None:

    '''
    safely writes a dictionary to a JSON file by creating a temporary file and atomically replacing the destination to prevent partial or corrupted writes
    '''

    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(dest.parent), encoding="utf-8") as tmp:
        json.dump(obj, tmp, indent=2 if pretty else None, separators=None if pretty else (",", ":"))
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, dest)

def export_settings(
    dest_path: str | os.PathLike,
    *,
    settings_file: str | os.PathLike = "settings.json",
    include_keys: Optional[Iterable[str]] = None,
    overwrite: bool = False,
    pretty: bool = True,
) -> Path:
    '''
    copies the current settings JSON to a specified destination file, with options to filter keys, format output, and control overwriting    dest = Path(dest_path)
    '''
    dest = Path(dest_path)
    if dest.exists() and dest.is_dir():
        raise IsADirectoryError(f"dest_path points to a directory, expected a file: {dest}")

    if dest.exists() and not overwrite:
        raise FileExistsError(f"Destination already exists: {dest}")

    settings = _load_settings_dict(settings_file)

    if include_keys is not None:
        subset = {}
        for k in include_keys:
            val = read_settings(k, settings_file=settings_file)
            if val is not None:
                subset[k] = val
        settings = subset

    _atomic_write_json(settings, dest, pretty=pretty)
    return dest

def import_settings(
    src_path: str | os.PathLike,
    *,
    settings_file: str | os.PathLike = "settings.json",
    merge: bool = False,
    pretty: bool = True
) -> Path:
    """
    import_settings loads a settings JSON file from a given location and updates the app’s main settings file, with options to merge, back up, and format the data safely.
    """
    src = Path(src_path).expanduser().resolve()
    dest = Path(settings_file).expanduser().resolve()

    if not src.exists():
        raise FileNotFoundError(f"Import source not found: {src}")

    try:
        with src.open("r", encoding="utf-8") as f:
            imported = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Import source is not valid JSON: {src}") from e

    if merge and dest.exists():
        try:
            with dest.open("r", encoding="utf-8") as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            existing = {}
        merged = {**existing, **imported}
    else:
        merged = imported

    _atomic_write_json(merged, dest, pretty=pretty)
    return dest
