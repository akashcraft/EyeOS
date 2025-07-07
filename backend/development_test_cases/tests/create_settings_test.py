import unittest
import json
import os
import shutil
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../services')))

from settings import create_settings  

class TestCreateSettings(unittest.TestCase):
    def setUp(self):
        self.test_settings = '../actual_results/create_settings_test/test_settings.json'
        self.test_default_settings = '../actual_results/create_settings_test/test_default_settings.json'
        self.expected_settings = '../expected_results/create_settings_test/expected_settings.json'
        self.expected_default_settings = '../expected_results/create_settings_test/expected_default_settings.json'

        expected_data = {
            "theme": "dark"
        }
        with open(self.expected_settings, 'w') as f:
            json.dump(expected_data, f, indent=4)
        shutil.copy(self.expected_settings, self.expected_default_settings)

    def test_create_settings(self):
        create_settings("theme", "dark", self.test_settings, self.test_default_settings)

        with open(self.test_settings) as f:
            actual_settings = json.load(f)
        with open(self.test_default_settings) as f:
            actual_default_settings = json.load(f)
        with open(self.expected_settings) as f:
            expected_settings = json.load(f)
        with open(self.expected_default_settings) as f:
            expected_default_settings = json.load(f)

        self.assertEqual(actual_settings, expected_settings)
        self.assertEqual(actual_default_settings, expected_default_settings)

    def tearDown(self):
        for f in [self.test_settings, self.test_default_settings,
                  self.expected_settings, self.expected_default_settings]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists('test_data'):
            os.rmdir('test_data')

if __name__ == '__main__':
    unittest.main()