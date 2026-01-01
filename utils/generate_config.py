import os
import json
import platform
from gits.config import MAIN_PATH

if platform.system() == "Windows":
    default_lean_path = r"C:\lean"
else:
    # Linux: ~/lean
    default_lean_path = os.path.join(os.path.expanduser("~"), "lean")

default_config = {
    "lean": {
        "lean_remote_ip": "10.5.0.198",
        "lean_remote_user": "sia8",
        "lean_remote_pwd": "a8_win10_share",
        "lean_remote_path": r"C:\Users\sia8\zkcc\lean",
        "lean_local_path": default_lean_path
    },
}


def gene_conf(parent_dir):
    if not os.path.exists(parent_dir):
        # 容错创建父目录
        try: os.makedirs(parent_dir, exist_ok=True)
        except: raise FileNotFoundError(f"Directory {parent_dir} not found")

    config_dir = os.path.join(parent_dir, "conf")
    config_path = os.path.join(parent_dir, "conf", "config.json")

    if not os.path.exists(config_dir):
        try:
            os.makedirs(config_dir)
            print(f"Created directory: {config_dir}")
        except Exception as e:
            print(f"Error creating directory {config_dir}: {e}")
            return

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        print(f"The configuration file has been generated：{config_path}")
    except Exception as e:
        print(f"error:{e}")
        print(f"Fatal: failed to write the configuration file")
        return