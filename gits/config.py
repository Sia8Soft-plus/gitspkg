import os
import sys
import json
import argparse

if getattr(sys, 'frozen', False):
    # 打包模式：sys.executable 是可执行文件
    # base_dir 应该是可执行文件所在的目录
    base_dir = os.path.dirname(os.path.abspath(sys.executable))
else:
    # 脚本开发模式：当前文件是 gits/config.py
    # 根目录是 gits/config.py 的上级(gits)的上级(root)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAIN_PATH = base_dir
CONFIG_PATH = os.path.join(base_dir, "conf", "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        # 容错：尝试在当前目录查找 (以防 config.json 没被放进 conf 文件夹)
        alt_path = os.path.join(base_dir, "config.json")
        if os.path.exists(alt_path):
            with open(alt_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        # 如果找不到，抛出异常让 commands.py 捕获并生成
        raise FileNotFoundError(f"Configuration file not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    conf_dir = os.path.dirname(CONFIG_PATH)
    if not os.path.exists(conf_dir):
        os.makedirs(conf_dir, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)


def execute_configs(args):
    try:
        config = load_config()
    except:
        return False

    lean_config = config["lean"]
    param_map = {
        "set_lean_remote_ip": "lean_remote_ip",
        "set_lean_remote_user": "lean_remote_user",
        "set_lean_remote_pwd": "lean_remote_pwd",
        "set_lean_remote_path": "lean_remote_path",
        "set_lean_local_path": "lean_local_path",
        "lean_remote_ip": "lean_remote_ip",
        "lean_remote_user": "lean_remote_user",
        "lean_remote_pwd": "lean_remote_pwd",
        "lean_remote_path": "lean_remote_path",
        "lean_local_path": "lean_local_path"
    }

    for param in ["set_lean_remote_ip", "set_lean_remote_user", "set_lean_remote_pwd",
                  "set_lean_remote_path", "set_lean_local_path"]:
        value = getattr(args, param)
        if value:
            key = param_map[param]
            lean_config[key] = value
            save_config(config)
            print(f"set successful [{key} = {value}]")
            return True

    for flag in ["lean_remote_ip", "lean_remote_user", "lean_remote_pwd",
                 "lean_remote_path", "lean_local_path"]:
        if getattr(args, flag):
            key = param_map[flag]
            print(f"{key} = {lean_config[key]}")
            return True

    return False


def show_config(conf=None):
    try:
        config = load_config()
    except:
        return None

    lean_config = config.get("lean", {})
    base_url = config.get("base_url")

    if conf:
        if conf == "base_url": return base_url
        return lean_config.get(conf)

    print("Base URL:", base_url)
    for key, value in lean_config.items():
        print(f"{key}={value}")