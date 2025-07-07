'''
This file is used to manage settings in the EyeOS application.

Functions include:
    create_settings()
    read_settings()
    write_settings()
    reset_demo()
    check_resource()
'''

import json
import os

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

def read_settings(setting_name, settings_file='settings.json'):
    '''
    This is used to read setting values in only the current settings file
    '''
    if not os.path.exists(settings_file):
        return None

    with open(settings_file, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return None

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
    
