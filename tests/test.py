from cwm.storage_manager import StorageManager
import json

sm = StorageManager()

# Update
sm.update_config("theme", "dark")

# Load updated version
config = sm.get_config()

# print(config)             # prints as Python dict
print(json.dumps(config, indent=2))   # prints pretty JSON

