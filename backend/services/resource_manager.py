import os
import json

class ResourceManager:
    def __init__(self, json_path='resources.json', default_resource_dir='../../resources'):
        self.json_path = json_path
        self.default_resource_dir = os.path.normpath(default_resource_dir)

        if not os.path.exists(self.json_path):
            with open(self.json_path, 'w') as f:
                json.dump([], f)

    def add_resource(self, file_name):
        """Add a new file name to the resource list."""
        with open(self.json_path, 'r+') as f:
            data = json.load(f)
            if file_name not in data:
                data.append(file_name)
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
                print(f"Added: {file_name}")
            else:
                print(f"{file_name} already exists in resource list.")

    def remove_resource(self, file_name):
        """Remove a file name from the resource list."""
        with open(self.json_path, 'r+') as f:
            data = json.load(f)
            if file_name in data:
                data.remove(file_name)
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
                print(f"Removed: {file_name}")
            else:
                print(f"{file_name} not found in resource list.")

    def verify_resources(self, resource_dir=None):
        """Check if all resources in JSON exist in the given or default resource folder."""
        check_dir = os.path.normpath(resource_dir) if resource_dir else self.default_resource_dir

        with open(self.json_path, 'r') as f:
            resource_list = json.load(f)

        missing_files = []
        for file_name in resource_list:
            full_path = os.path.join(check_dir, file_name)
            if not os.path.exists(full_path):
                missing_files.append(file_name)

        if missing_files:
            print(f"Missing resources in {check_dir}:")
            for file in missing_files:
                print(f" - {file}")
            return False
        else:
            print(f"All resources are present in {check_dir}.")
            return True

# Use this to test the functions 
if __name__ == "__main__":
    rm = ResourceManager()
    rm.add_resource("Dummy.png")
    rm.verify_resources()
    rm.remove_resource("Dummy.png")
    rm.verify_resources()

