import unittest
import os
import json
import shutil
from resource_manager import ResourceManager

class TestResourceManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs('test_resources', exist_ok=True)
        cls.test_json = 'test_resources.json'
        cls.test_dir = 'test_resources'
        cls.existing_file = 'image.png'
        cls.missing_file = 'ghost.gif'

        with open(os.path.join(cls.test_dir, cls.existing_file), 'w') as f:
            f.write("fake image content")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_json):
            os.remove(cls.test_json)
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def setUp(self):
        self.rm = ResourceManager(json_path=self.test_json, default_resource_dir=self.test_dir)

    def test_add_resource(self):
        self.rm.add_resource(self.existing_file)
        with open(self.test_json, 'r') as f:
            data = json.load(f)
        self.assertIn(self.existing_file, data)

    def test_no_duplicate_resources(self):
        self.rm.add_resource(self.existing_file)
        self.rm.add_resource(self.existing_file)
        with open(self.test_json, 'r') as f:
            data = json.load(f)
        self.assertEqual(data.count(self.existing_file), 1)

    def test_remove_resource(self):
        self.rm.add_resource(self.existing_file)
        self.rm.remove_resource(self.existing_file)
        with open(self.test_json, 'r') as f:
            data = json.load(f)
        self.assertNotIn(self.existing_file, data)

    def test_remove_nonexistent_resource(self):
        # Should not raise an error
        self.rm.remove_resource("not_in_list.png")
        with open(self.test_json, 'r') as f:
            data = json.load(f)
        self.assertNotIn("not_in_list.png", data)

    def test_verify_resources_with_all_present(self):
        self.rm.add_resource(self.existing_file)
        self.rm.verify_resources(self.test_dir)

    def test_verify_resources_with_missing_file(self):
        self.rm.add_resource(self.missing_file)
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output

        self.rm.verify_resources(self.test_dir)

        sys.stdout = sys.__stdout__ 
        output = captured_output.getvalue()
        self.assertIn("Missing resources", output)
        self.assertIn(self.missing_file, output)

if __name__ == '__main__':
    unittest.main()
