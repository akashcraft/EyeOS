from backend.services import settings
settings_file = './backend/services/settings.json'

camera_input_changed = False
eyebrow_scroll_enabled = False
lip_scroll_enabled = settings.read_settings("scroll_mode", settings_file) == 1
lip_brow_scroll_enabled = settings.read_settings("scroll_mode", settings_file) == 2
blink_enabled = settings.read_settings("blink_mode", settings_file) == 0
gaze_hold_enabled = settings.read_settings("blink_mode", settings_file) == 1
mouth_click_enabled = settings.read_settings("blink_mode", settings_file) == 2
