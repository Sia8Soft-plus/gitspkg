import ast
import glob
import json
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import zipfile
import os
import sys
import paramiko
import rarfile
from packaging.version import parse as parse_version, InvalidVersion

from py7zr import py7zr
from tqdm import tqdm
from colorama import Fore, Style, init
from datetime import datetime
from gits.config import show_config

# --- 【配置】平台与编码 ---
SYSTEM_NAME = platform.system()
IS_WINDOWS = (SYSTEM_NAME == "Windows")
# 动态定义系统编码：Windows用gbk，Linux用utf-8
SYS_ENCODING = 'gbk' if IS_WINDOWS else 'utf-8'

import ctypes

# 仅在 Windows 下导入 winreg
if IS_WINDOWS:
    try:
        import winreg
    except ImportError:
        pass

import atexit

init()

lean_remote_ip = show_config("lean_remote_ip")
lean_remote_user = show_config("lean_remote_user")
lean_remote_pwd = show_config("lean_remote_pwd")
l_r_p = show_config("lean_remote_path")
lean_local_path = show_config("lean_local_path")

workspace_path = os.path.join(os.getcwd(), 'workspace')
unresolved_packages = []
missing_packages = []
missing_packages_ = []
need_update_packages = []
need_update_packages_ = []
extra_command_ = ["IGNORE_IN_DEPENDENCY"]

_GLOBAL_SSH = None
_GLOBAL_SFTP = None
_CACHED_REMOTE_PATH = None

_CACHE_SERVER_PACKAGES = None
_CACHE_MANIFEST_DEPS = {}
_CACHE_LOCAL_PACKAGES = None


def get_sftp_session():
    """获取全局唯一的 SFTP 会话"""
    global _GLOBAL_SSH, _GLOBAL_SFTP

    if _GLOBAL_SSH and _GLOBAL_SFTP:
        try:
            if _GLOBAL_SSH.get_transport().is_active():
                return _GLOBAL_SFTP
        except:
            pass

    print("Connecting to lean server...")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(lean_remote_ip, username=lean_remote_user, password=lean_remote_pwd)
        sftp = ssh.open_sftp()

        _GLOBAL_SSH = ssh
        _GLOBAL_SFTP = sftp
        return sftp
    except Exception as e:
        print(Fore.RED + f"Connection failed: {e}" + Style.RESET_ALL)
        return None


def close_sftp_session():
    global _GLOBAL_SSH, _GLOBAL_SFTP
    if _GLOBAL_SFTP: _GLOBAL_SFTP.close()
    if _GLOBAL_SSH: _GLOBAL_SSH.close()


atexit.register(close_sftp_session)


# --- 【核心修改】环境变量配置 (Linux 适配) ---
def add_to_system_path_env(new_path):
    """
    将路径写入系统环境变量。
    Windows: 注册表
    Linux: /etc/profile.d/gis_lean_paths.sh
    """
    new_path = os.path.abspath(new_path)

    if IS_WINDOWS:
        # Windows 逻辑
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except:
            is_admin = False

        if not is_admin:
            print(Fore.RED + "Error: Writing to System Path requires Administrator privileges." + Style.RESET_ALL)
            return False

        REG_PATH = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_ALL_ACCESS)
            try:
                current_path, path_type = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""
                path_type = winreg.REG_EXPAND_SZ

            path_list = [p.strip() for p in current_path.split(';') if p.strip()]
            norm_path_list = [os.path.normpath(p).lower() for p in path_list]

            if os.path.normpath(new_path).lower() in norm_path_list:
                winreg.CloseKey(key)
                return False

            if current_path and not current_path.endswith(';'):
                current_path += ';'
            new_path_value = current_path + new_path

            winreg.SetValueEx(key, "Path", 0, path_type, new_path_value)
            winreg.CloseKey(key)

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            result = ctypes.c_long()
            try:
                ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, u"Environment",
                                                         SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
            except:
                pass
            os.environ["PATH"] += os.pathsep + new_path
            return True
        except PermissionError:
            print(Fore.RED + "Permission Denied: Please run as Administrator." + Style.RESET_ALL)
            return False
        except Exception as e:
            print(Fore.RED + f"Failed to write system environment variable: {e}" + Style.RESET_ALL)
            return False

    else:
        # Linux 逻辑
        LINUX_ENV_FILE = "/etc/profile.d/gis_lean_paths.sh"

        # 简单查重
        current_paths = os.environ.get("PATH", "").split(":")
        if new_path in current_paths:
            return False

        file_content = ""
        if os.path.exists(LINUX_ENV_FILE):
            try:
                with open(LINUX_ENV_FILE, 'r') as f:
                    file_content = f.read()
            except:
                pass

        if new_path in file_content:
            return False

        export_cmd = f'\nexport PATH=$PATH:"{new_path}"'

        try:
            with open(LINUX_ENV_FILE, 'a') as f:
                f.write(export_cmd)
            os.chmod(LINUX_ENV_FILE, 0o644)
            # 临时生效
            os.environ["PATH"] += os.pathsep + new_path
            return True
        except PermissionError:
            print(
                Fore.RED + f"Permission Denied: Cannot write to {LINUX_ENV_FILE}. Sudo required to update PATH." + Style.RESET_ALL)
            return False
        except Exception as e:
            print(Fore.RED + f"Failed to update Linux PATH: {e}" + Style.RESET_ALL)
            return False


def get_system_path_env():
    """获取系统级持久化的 PATH 变量"""
    if IS_WINDOWS:
        REG_PATH = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_READ)
            try:
                path_value, _ = winreg.QueryValueEx(key, "Path")
                return path_value
            except FileNotFoundError:
                return ""
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            print(f"Error reading registry: {e}")
            return ""
    else:
        return os.environ.get("PATH", "")


def check_lean_remote_path(l_r_p):
    if not l_r_p.endswith('/'):
        l_r_p += '/'
    return l_r_p


def get_local_os_info():
    """获取本地操作系统信息"""
    system = platform.system().lower()

    if system == "linux":
        try:
            with open("/etc/os-release") as f:
                lines = f.readlines()
            info = {k.strip(): v.strip().strip('"') for k, v in
                    [line.split('=', 1) for line in lines if '=' in line]}
            os_name = info.get("ID", "linux")
            os_version = info.get("VERSION_ID", platform.release())
            return os_name, os_version
        except FileNotFoundError:
            return "linux", platform.release()

    elif system == "windows":
        try:
            version_parts = platform.version().split('.')
            if len(version_parts) >= 3:
                build_number = int(version_parts[2])
                if build_number >= 22000:
                    return "windows", "11"
        except (ValueError, IndexError):
            pass
        return "windows", platform.release()

    elif system == "darwin":
        mac_ver = platform.mac_ver()[0]
        return "macos", mac_ver.split('.')[0]

    else:
        return system, platform.release()


def find_best_os_dir(available_dirs):
    """根据本地系统匹配最佳远程目录（含 Linux 泛化回退逻辑）"""
    local_os_name, local_os_version_str = get_local_os_info()
    print(f"Local system detected: {local_os_name}-{local_os_version_str}")
    try:
        local_os_version = parse_version(local_os_version_str)
    except InvalidVersion:
        return None, f"Error: The local system version '{local_os_version_str}' could not be parsed."

    os_matched_candidates = []  # 优先级1：名字匹配的
    linux_fallback_candidates = []  # 优先级2：Linux 跨发行版回退的

    for dir_name in available_dirs:
        try:
            parts = dir_name.rsplit('-', 1)
            if len(parts) != 2: continue
            remote_os, remote_version_str = parts

            try:
                remote_version = parse_version(remote_version_str)
            except InvalidVersion:
                continue

            # --- 1. 精确/模糊名称匹配 (优先级最高) ---
            # 例如：本地 ubuntu 匹配 远程 ubuntu-xx
            if remote_os.lower() in local_os_name.lower() or local_os_name.lower() in remote_os.lower():
                os_matched_candidates.append({
                    "dir_name": dir_name,
                    "version": remote_version
                })

            # --- 2. Linux 泛化回退逻辑 (新增) ---
            # 条件：本地是 Linux (非Win/Mac)，且没有命中上面的精确匹配
            # 且远程目录名包含 'mint' (针对你的 mint6.8.0-51) 或者 'linux'
            elif (local_os_name not in ['windows', 'macos']) and \
                    ('mint' in remote_os.lower() or 'linux' in remote_os.lower()):
                linux_fallback_candidates.append({
                    "dir_name": dir_name,
                    "version": remote_version
                })

        except ValueError:
            continue

    # 决策：如果有精确匹配，只看精确匹配；否则看回退候选项
    candidates_to_use = []
    if os_matched_candidates:
        candidates_to_use = os_matched_candidates
    elif linux_fallback_candidates:
        print(
            Fore.YELLOW + f"Info: No exact OS match for '{local_os_name}'. Fallback to Linux compatible directory." + Style.RESET_ALL)
        candidates_to_use = linux_fallback_candidates
    else:
        return None, f"Match failed: No packages related to '{local_os_name}' found."

    exact_match = None
    best_older_candidate = None
    best_newer_candidate = None

    for candidate in candidates_to_use:
        if candidate["version"] == local_os_version:
            exact_match = candidate
            break
        if candidate["version"] < local_os_version:
            if best_older_candidate is None or candidate["version"] > best_older_candidate["version"]:
                best_older_candidate = candidate
        else:
            if best_newer_candidate is None or candidate["version"] < best_newer_candidate["version"]:
                best_newer_candidate = candidate

    if exact_match:
        return exact_match["dir_name"], "Found an exact version match."
    if best_older_candidate:
        return best_older_candidate["dir_name"], "Success: Found the closest backward-compatible version."
    if best_newer_candidate:
        # 对于回退情况，版本号比较可能没有实际意义（例如 Ubuntu 22 vs Mint 51），
        # 但这仍能保证选出一个目录，只要该目录里的 GCC 版本对得上就能用。
        return best_newer_candidate["dir_name"], "Warning: Newer version selected."

    return None, "Match failed."

def match_lean_remote():
    global _CACHED_REMOTE_PATH
    if _CACHED_REMOTE_PATH: return _CACHED_REMOTE_PATH

    sftp = get_sftp_session()
    if not sftp: return None

    final_path = None
    try:
        base_remote_path = check_lean_remote_path(l_r_p)
        all_items = sftp.listdir_attr(base_remote_path)
        dir_list = [attr.filename for attr in all_items if stat.S_ISDIR(attr.st_mode)]
        best_dir_name, message = find_best_os_dir(dir_list)

        if best_dir_name:
            final_path = base_remote_path + best_dir_name
            try:
                sftp.stat(final_path)
                _CACHED_REMOTE_PATH = final_path
            except:
                final_path = None
    except Exception as e:
        print(f"Remote match error: {e}")

    return final_path


lean_remote_path = None


# --- 【核心修改】 编译器识别与正则 ---
def get_vs_version():
    """
    获取默认编译器版本标签。
    Windows: [VS2019] (或检测到的版本)
    Linux: [GCC12.3.0]
    """
    # Windows 下的默认值
    default_version_win = "[VS2019]"
    # Linux 下的默认值
    default_version_linux = "[GCC12.3.0]"

    if not IS_WINDOWS:
        return default_version_linux

    # --- Windows 检测逻辑 ---
    vs_main_to_year = {
        "15": "2017",
        "16": "2019",
        "17": "2022",
        "18": "2024"
    }

    env_ver = os.environ.get("VisualStudioVersion")
    if env_ver:
        major = env_ver.split('.')[0]
        if major in vs_main_to_year:
            return f"[VS{vs_main_to_year[major]}]"

    ps_command = (
        "Get-CimInstance MSFT_VSInstance -Namespace root/cimv2/vs -ErrorAction SilentlyContinue "
        "| Select-Object Version, Name "
        "| ConvertTo-Json -Compress"
    )

    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            encoding="utf-8",
            errors="ignore",
            check=False
        )
        if not result.stdout or result.returncode != 0:
            return default_version_win

        try:
            vs_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return default_version_win

        vs_instances = [vs_data] if isinstance(vs_data, dict) else vs_data
        valid_years = set()
        for instance in vs_instances:
            year = None
            version_full = instance.get("Version", "")
            if version_full:
                main_version = str(version_full).split(".")[0]
                year = vs_main_to_year.get(main_version)
            if not year:
                name_str = instance.get("Name", "")
                year_match = re.search(r"20\d{2}", name_str)
                if year_match:
                    year = year_match.group()
            if year in ["2017", "2019", "2022", "2024"]:
                valid_years.add(year)
        if valid_years:
            return f"[VS{max(valid_years)}]"
        return default_version_win
    except Exception:
        return default_version_win


def get_project_compiler(manifest_directory, manifest_filename):
    """读取 manifest 文件获取编译器标签"""
    system_vs_tag = get_vs_version()

    # 简单的正则判断是否包含 []
    if system_vs_tag and system_vs_tag.startswith('[') and system_vs_tag.endswith(']'):
        default_compiler = system_vs_tag[1:-1]
    else:
        default_compiler = "VS2019" if IS_WINDOWS else "GCC12.3.0"

    if manifest_filename == None:
        return default_compiler

    manifest_path = os.path.join(manifest_directory, manifest_filename)

    if not os.path.exists(manifest_path):
        return default_compiler

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '#' in line:
                    line = line.split('#', 1)[0]
                line = line.strip()
                if not line: continue

                # 【正则修改】同时支持 VS数字 和 GCC数字.点
                # 例如: [VS2019] 或 [GCC12.3.0]
                match = re.match(r'^\[(VS\d+|GCC[\d\.]+)\]$', line, re.IGNORECASE)
                if match:
                    return match.group(1).upper()
                else:
                    return default_compiler
    except Exception:
        pass
    return default_compiler


def find_real_package_key(pkg_name, pkg_version_str, local_lookup, local_packages):
    if pkg_name not in local_lookup:
        return None
    candidates = local_lookup[pkg_name]
    if not pkg_version_str:
        return max(candidates, key=lambda k: local_packages[k]['version'])

    try:
        req_ver_obj = parse_version(pkg_version_str)
        for key in candidates:
            if local_packages[key]['version'] == req_ver_obj:
                return key
    except InvalidVersion:
        pass
    return None


def get_local_packages(force_refresh=False):
    global _CACHE_LOCAL_PACKAGES
    if _CACHE_LOCAL_PACKAGES is not None and not force_refresh:
        return _CACHE_LOCAL_PACKAGES

    packages = {}
    if not os.path.isdir(lean_local_path):
        _CACHE_LOCAL_PACKAGES = packages
        return packages

    for dir_name in os.listdir(lean_local_path):
        full_path = os.path.join(lean_local_path, dir_name)

        if os.path.isdir(full_path):
            try:
                compiler_tag = "Unknown"
                name_ver_part = dir_name

                # 【正则修改】匹配后缀 -VS2019, -GCC12.3.0
                # 支持包含数字和点号的编译器名
                compiler_match = re.search(r'[-@](VS\d+|GCC[\d\.]+|CLANG[\d\.]+|GCC)$', dir_name, re.IGNORECASE)

                if compiler_match:
                    compiler_tag = compiler_match.group(1).upper()
                    name_ver_part = dir_name[:compiler_match.start()]

                if '@' in name_ver_part:
                    pkg_name, version_str = name_ver_part.split('@', 1)
                elif '-' in name_ver_part:
                    pkg_name, version_str = name_ver_part.rsplit('-', 1)
                else:
                    continue

                version_obj = parse_version(version_str)
                update_time = datetime.fromtimestamp(os.path.getmtime(full_path))
                unique_key = f"{pkg_name}@{version_str}@{compiler_tag}"

                version_info = {
                    'name': pkg_name,
                    'version': version_obj,
                    'version_str': version_str,
                    'compiler': compiler_tag,
                    'full_path': full_path,
                    'time': update_time
                }
                packages[unique_key] = version_info

            except (InvalidVersion, ValueError):
                pass

    _CACHE_LOCAL_PACKAGES = packages
    return packages


def get_server_packages(sftp, lean_remote_path, packages_dict=None):
    global _CACHE_SERVER_PACKAGES
    if packages_dict is None:
        if _CACHE_SERVER_PACKAGES is not None:
            return _CACHE_SERVER_PACKAGES
        packages_dict = {}
        is_root_call = True
    else:
        is_root_call = False

    try:
        global _GLOBAL_SSH
        if not _GLOBAL_SSH:
            get_sftp_session()

        if _GLOBAL_SSH:
            cmd = f'find {lean_remote_path} -type f \\( -name "*.zip" -o -name "*.tar" \\) -printf "%p|%T@\\n"'
            stdin, stdout, stderr = _GLOBAL_SSH.exec_command(cmd)
            file_list = stdout.read().decode().splitlines()

            for line in file_list:
                line = line.strip()
                if not line or '|' not in line: continue

                full_path, timestamp_str = line.split('|')

                try:
                    parts = full_path.split('/')
                    if len(parts) < 4: continue

                    channel = parts[-2]
                    package_name = parts[-3]
                    compiler_name = parts[-4]

                    if channel in ('stable', 'common'):
                        filename = parts[-1]
                        filename_no_ext = os.path.splitext(filename)[0]
                        if filename_no_ext.endswith('.tar'):
                            filename_no_ext = os.path.splitext(filename_no_ext)[0]

                        if '@' in filename_no_ext:
                            _, version_str = filename_no_ext.split('@', 1)
                        else:
                            _, version_str = filename_no_ext.rsplit('-', 1)

                        version_obj = parse_version(version_str)
                        file_time = datetime.fromtimestamp(float(timestamp_str))

                        version_info = {
                            'version': version_obj,
                            'version_str': version_str,
                            'location': channel,
                            'compiler': compiler_name,
                            'full_path': full_path,
                            'time': file_time
                        }
                        packages_dict.setdefault(package_name, []).append(version_info)
                except (ValueError, InvalidVersion, IndexError):
                    continue
        else:
            print(Fore.RED + "SSH session lost, cannot scan packages." + Style.RESET_ALL)

    except Exception as e:
        print(f"Error executing find command: {e}")

    if is_root_call:
        _CACHE_SERVER_PACKAGES = packages_dict

    return packages_dict


def get_lean_mainfest_packages(args, manifest_directory, root_only=False, sftp=None, lean_remote_path=None):
    global _CACHE_MANIFEST_DEPS
    file_key = tuple(sorted(args.target_manifests)) if args.target_manifests else "default"
    cache_key = (file_key, root_only)

    if cache_key in _CACHE_MANIFEST_DEPS:
        return _CACHE_MANIFEST_DEPS[cache_key]

    requirements_list = []
    found_manifest = False
    target_subdir = 'dependency'

    for root, dirs, files in os.walk(manifest_directory):
        if root_only:
            if root == manifest_directory: dirs[:] = []
        else:
            if os.path.basename(root).lower() != target_subdir:
                dirs[:] = [d for d in dirs if d.lower() == target_subdir]

        if root_only and root != manifest_directory: continue

        is_root_directory = (root == manifest_directory)
        for file in files:
            should_process_file = False
            if is_root_directory:
                if file in args.target_manifests: should_process_file = True
            else:
                if file.endswith('.manifest'): should_process_file = True

            if should_process_file:
                found_manifest = True
                manifest_path = os.path.join(root, file)
                try:
                    with open(manifest_path, 'r', encoding='utf-8-sig') as f:
                        content = f.read().strip().splitlines()
                        for line in content:
                            if '#' in line: line = line.split('#', 1)[0]
                            if not line: continue
                            line = line.strip().replace("IGNORE_IN_DEPENDENCY", "").strip()
                            if not line or line.startswith('#') or line.startswith('[') or \
                                    line.startswith(('http://', 'https://')) or line.endswith('.git') or \
                                    line.lower().startswith(('copy ', 'move ')):
                                continue
                            pkg_part = line.split(':', 1)[0].strip()
                            if '==' in pkg_part:
                                parts = pkg_part.split('==', 1)
                                name, ver = parts[0].strip(), parts[1].strip()
                            else:
                                name, ver = pkg_part, None
                            if name:
                                item = {'name': name, 'version': ver}
                                if item not in requirements_list:
                                    requirements_list.append(item)
                except Exception as e:
                    print(f"Error reading manifest file {manifest_path}: {e}")

    if not found_manifest:
        # print(f"The manifest file '{args.manifest_filename}' was not found in the project.")
        pass

    remote_copy_cmds = {}

    if sftp and lean_remote_path:
        stack = [item.copy() for item in requirements_list]
        checked_keys = set()
        dep_tree_base = f"{lean_remote_path}/dep_tree"

        while stack:
            current_item = stack.pop()
            current_pkg = current_item['name']
            current_ver = current_item['version']

            current_key = f"{current_pkg}@{current_ver}" if current_ver else current_pkg
            if current_key in checked_keys: continue
            checked_keys.add(current_key)

            candidates = []
            if current_ver:
                candidates.append(f"{dep_tree_base}/{current_pkg}@{current_ver}.dep")
            candidates.append(f"{dep_tree_base}/{current_pkg}.dep")

            file_handle = None
            found_dep_path = None
            for remote_dep_file in candidates:
                try:
                    file_handle = sftp.open(remote_dep_file)
                    found_dep_path = remote_dep_file
                    break
                except IOError:
                    continue

            if not file_handle: continue

            try:
                with file_handle as f:
                    remote_context_tuple = None

                    for line in f:
                        if isinstance(line, bytes):
                            try:
                                line = line.decode('utf-8-sig')
                            except:
                                line = line.decode('utf-8')
                        if '#' in line: line = line.split('#', 1)[0]
                        if not line: continue
                        line = line.strip().replace("IGNORE_IN_DEPENDENCY", "").strip()
                        if not line or line.startswith('#') or line.startswith('[') or \
                                line.startswith(('http://', 'https://')) or line.endswith('.git'):
                            continue

                        if line.lower().startswith(('copy ', 'move ')):
                            if remote_context_tuple:
                                remote_copy_cmds.setdefault(remote_context_tuple, []).append(line)
                            continue

                        pkg_part = ""
                        cmd_part = None
                        if ':' in line:
                            parts = line.split(':', 1)
                            pkg_part = parts[0].strip()
                            cmd_part = parts[1].strip()
                        else:
                            pkg_part = line

                        if '==' in pkg_part:
                            parts = pkg_part.split('==', 1)
                            dep_name, dep_version = parts[0].strip(), parts[1].strip()
                        else:
                            dep_name, dep_version = pkg_part, None
                        if not dep_name: continue

                        item = {'name': dep_name, 'version': dep_version}
                        if item not in requirements_list:
                            requirements_list.append(item)

                        remote_context_tuple = (dep_name, dep_version)

                        if cmd_part and cmd_part.lower().startswith(('copy', 'move')):
                            remote_copy_cmds.setdefault(remote_context_tuple, []).append(cmd_part)

                        dep_key = f"{dep_name}@{dep_version}" if dep_version else dep_name
                        if dep_key not in checked_keys:
                            stack.append(item)
            except Exception as e:
                print(f"Warning: Error parsing dep file {found_dep_path}: {e}")

    _CACHE_MANIFEST_DEPS[cache_key] = (requirements_list, remote_copy_cmds)
    return requirements_list, remote_copy_cmds


def execute_remote_copy(repo_path, remote_copy_cmds):
    if not remote_copy_cmds: return

    local_packages = get_local_packages()
    local_lookup = {}
    for unique_key, info in local_packages.items():
        if info.get('name'):
            local_lookup.setdefault(info['name'], []).append(unique_key)

    for (pkg_name, pkg_version), cmds in remote_copy_cmds.items():
        real_unique_key = find_real_package_key(pkg_name, pkg_version, local_lookup, local_packages)

        if not real_unique_key:
            ver_msg = f"@{pkg_version}" if pkg_version else ""
            print(
                Fore.YELLOW + f"Warning: Cannot execute remote copy for '{pkg_name}{ver_msg}', package not found locally." + Style.RESET_ALL)
            continue

        base_source_dir = local_packages[real_unique_key]['full_path']

        for operation in cmds:
            try:
                match = re.match(r'(?P<command>\w+)\s+(?P<source>.+?)\s+to\s+(?P<destination>[^\s]+)', operation)
                if match:
                    command, source, dest = match.group('command'), match.group('source'), match.group('destination')
                    abs_dest = os.path.join(repo_path, dest)
                    os.makedirs(abs_dest, exist_ok=True)
                    full_source = os.path.join(base_source_dir, source)
                    items = glob.glob(full_source)
                    if items:
                        print(f"Executing {pkg_name}: {command} {source} -> {dest}")
                        for item in items:
                            if command == "copy":
                                if os.path.isfile(item):
                                    shutil.copy2(item, abs_dest)
                                elif os.path.isdir(item):
                                    shutil.copytree(item, os.path.join(abs_dest, os.path.basename(item)),
                                                    dirs_exist_ok=True)
                            elif command == "move":
                                shutil.move(item, abs_dest)
            except Exception as e:
                print(f"Error executing remote copy: {e}")


def get_lean_mainfest_depurl(args, manifest_directory, root_only=False):
    manifests_url = []
    git_url_pattern = re.compile(r"^https?://[\w.-]+(:\d+)?/.+\.git")
    found_manifest = False
    target_subdir = 'dependency'

    for root, dirs, files in os.walk(manifest_directory):
        if root_only:
            if root == manifest_directory:
                dirs[:] = []
        else:
            if os.path.basename(root).lower() != target_subdir:
                dirs[:] = [d for d in dirs if d.lower() == target_subdir]
        if root_only and root != manifest_directory:
            continue
        is_root_directory = (root == manifest_directory)

        for file in files:
            should_process_file = False
            if is_root_directory:
                if file in args.target_manifests:
                    should_process_file = True
            else:
                if file.endswith('.manifest'):
                    should_process_file = True

            if should_process_file:
                found_manifest = True
                manifest_path = os.path.join(root, file)
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip().splitlines()
                    for line in content:
                        if '#' in line:
                            line = line.split('#', 1)[0]
                        if not line:
                            continue
                        clean_line = line.strip()
                        if git_url_pattern.match(clean_line):
                            manifests_url.append(clean_line)

    if not found_manifest:
        pass

    return list(set(manifests_url))


def compare_packages(args, sftp, lean_remote_path):
    global unresolved_packages, missing_packages, missing_packages_, need_update_packages, need_update_packages_
    if getattr(args, 'compiler', None):
        target_compiler = args.compiler.upper()
    else:
        target_file = args.target_manifests[0] if args.target_manifests else args.manifest_filename
        target_compiler = get_project_compiler(os.getcwd(), target_file)

    print(f"Target Compiler: {Fore.CYAN}{target_compiler}{Style.RESET_ALL}")

    requirements, _ = get_lean_mainfest_packages(args, os.getcwd(), sftp=sftp, lean_remote_path=lean_remote_path)
    local_packages_map = get_local_packages()
    server_packages_map = get_server_packages(sftp, lean_remote_path)

    unresolved_packages, missing_packages, missing_packages_ = [], [], []
    need_update_packages, need_update_packages_ = [], []

    for req in requirements:
        pkg_name, req_version_str = req['name'], req['version']
        target_version_info = None

        if pkg_name not in server_packages_map:
            unresolved_packages.append(pkg_name)
            continue

        all_versions = server_packages_map[pkg_name]

        if req_version_str is not None:
            try:
                req_version_obj = parse_version(req_version_str)
                match = next(
                    (v for v in all_versions if v['version'] == req_version_obj and v['compiler'] == target_compiler),
                    None)

                if match:
                    target_version_info = match
                else:
                    match_any_compiler = next((v for v in all_versions if v['version'] == req_version_obj), None)
                    if match_any_compiler:
                        print(
                            Fore.YELLOW + f"Warning: Found '{pkg_name}=={req_version_str}' in '{match_any_compiler['compiler']}' (Target is {target_compiler}). Using it." + Style.RESET_ALL)
                        target_version_info = match_any_compiler

            except InvalidVersion:
                print(Fore.RED + f"Error: Invalid version format '{req_version_str}'" + Style.RESET_ALL)
                pass

        else:
            target_compiler_versions = [v for v in all_versions if v['compiler'] == target_compiler]

            def find_best_in_list(ver_list):
                stable = [v for v in ver_list if v['location'] == 'stable']
                common = [v for v in ver_list if v['location'] == 'common']
                if stable: return max(stable, key=lambda v: v['version'])
                if common: return max(common, key=lambda v: v['version'])
                return None

            if target_compiler_versions:
                target_version_info = find_best_in_list(target_compiler_versions)

            if not target_version_info:
                print(
                    Fore.YELLOW + f"Warning: No version found for '{pkg_name}' in {target_compiler}. Searching all compilers..." + Style.RESET_ALL)
                target_version_info = find_best_in_list(all_versions)

        if not target_version_info:
            req_str = f"=={req_version_str}" if req_version_str else ""
            unresolved_packages.append(f"{pkg_name}{req_str}")
            continue

        target_version_str = target_version_info['version_str']
        full_remote_path = target_version_info['full_path']
        server_time = target_version_info['time']
        found_compiler = target_version_info['compiler']

        target_key = f"{pkg_name}@{target_version_str}@{found_compiler}"

        if target_key not in local_packages_map:
            missing_packages.append(target_key)
            missing_packages_.append(full_remote_path)
        else:
            local_info = local_packages_map[target_key]
            if server_time > local_info['time']:
                print(f"{target_key} needs update.")
                need_update_packages.append(target_key)
                need_update_packages_.append(full_remote_path)


def progress_bar(current, total):
    if total > 0:
        percent = (current / total) * 100
        bar_length = 50
        block = int(bar_length * current // total)
        progress = "#" * block + "-" * (bar_length - block)
        print(f"\r[{progress}] {percent:.2f}%", end='')


def extract_file(file_path, extract_to):
    if file_path.endswith('.zip'):
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            total_files = len(zip_ref.namelist())
            with tqdm(total=total_files, desc="Unzipping", unit="file") as pbar:
                for file_info in zip_ref.infolist():
                    zip_ref.extract(file_info, extract_to)
                    pbar.update(1)
    elif file_path.endswith('.rar'):
        with rarfile.RarFile(file_path, 'r') as rar_ref:
            total_files = len(rar_ref.namelist())
            with tqdm(total=total_files, desc="Unzipping", unit="file") as pbar:
                for file_info in rar_ref.infolist():
                    rar_ref.extract(file_info, extract_to)
                    pbar.update(1)
    elif file_path.endswith('.tar') or file_path.endswith('.tar.gz') or file_path.endswith('.tgz'):
        with tarfile.open(file_path, 'r:*') as tar_ref:
            total_files = len(tar_ref.getmembers())
            with tqdm(total=total_files, desc="Unzipping", unit="file") as pbar:
                for member in tar_ref.getmembers():
                    tar_ref.extract(member, extract_to)
                    pbar.update(1)
    elif file_path.endswith('.7z'):
        with py7zr.SevenZipFile(file_path, mode='r') as archive:
            total_files = len(archive.getnames())
            with tqdm(total=total_files, desc="Unzipping", unit="file") as pbar:
                archive.extractall(path=extract_to)
                pbar.update(total_files)
    else:
        return
    try:
        os.remove(file_path)
    except Exception as e:
        print(f"Error deleting archive: {e}")


def download_package(sftp, full_remote_path):
    package_filename = os.path.basename(full_remote_path)
    filename_no_ext = os.path.splitext(package_filename)[0]
    if filename_no_ext.endswith('.tar'):
        filename_no_ext = os.path.splitext(filename_no_ext)[0]
    base_package_name = filename_no_ext

    # 【正则修改】支持 GCC12.3.0
    compiler_tag = "Unknown"
    match = re.search(r'/(VS\d+|GCC[\d\.]+|CLANG[\d\.]+|GCC)/', full_remote_path, re.IGNORECASE)
    if match:
        compiler_tag = match.group(1).upper()

    final_dir_name = f"{base_package_name}@{compiler_tag}"
    target_dir_path = os.path.join(lean_local_path, final_dir_name)
    local_zip_path = os.path.join(lean_local_path, package_filename)

    try:
        os.makedirs(os.path.dirname(local_zip_path), exist_ok=True)
        total_size = sftp.stat(full_remote_path).st_size
        print("-" * 35)
        print(f"Fetching: {final_dir_name} (Compiler: {compiler_tag})")
        sftp.get(full_remote_path, local_zip_path, callback=lambda x, y: progress_bar(x, total_size))
        print(f"\nDownload done!")
    except Exception as e:
        print(f"\nFetch failed! {e}")
        return 1, final_dir_name

    try:
        download_time = datetime.fromtimestamp(os.path.getmtime(local_zip_path)).isoformat()
        log_path = os.path.join(lean_local_path, "download.log")
        logs = {}
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                content = f.read()
                if content: logs = ast.literal_eval(content)
        logs[final_dir_name] = download_time
        with open(log_path, 'w') as f:
            f.write(str(logs))
    except Exception:
        pass

    if os.path.isdir(target_dir_path):
        shutil.rmtree(target_dir_path, ignore_errors=True)

    print(f"Unzipping to {final_dir_name}...")
    try:
        temp_extract_dir = os.path.join(lean_local_path, f"temp_{final_dir_name}")
        if os.path.isdir(temp_extract_dir): shutil.rmtree(temp_extract_dir)
        os.makedirs(temp_extract_dir, exist_ok=True)

        extract_file(local_zip_path, temp_extract_dir)

        extracted_items = os.listdir(temp_extract_dir)
        if not extracted_items: return 3, final_dir_name

        source_dir = temp_extract_dir
        if len(extracted_items) == 1:
            sub_path = os.path.join(temp_extract_dir, extracted_items[0])
            if os.path.isdir(sub_path):
                source_dir = sub_path

        shutil.move(source_dir, target_dir_path)

        if os.path.exists(temp_extract_dir): shutil.rmtree(temp_extract_dir)

        print(f"Installed successfully: {final_dir_name}")

        global _CACHE_LOCAL_PACKAGES
        _CACHE_LOCAL_PACKAGES = None

        return 2, final_dir_name

    except Exception as e:
        print(f"Unzip failed: {e}")
        return 3, final_dir_name


def process_manifests(args, manifest_directory):
    original_directory = os.getcwd()
    local_has_command_set = set()

    try:
        os.chdir(manifest_directory)
        package_operations = {}

        local_packages = get_local_packages()
        local_lookup = {}
        for unique_key, info in local_packages.items():
            pkg_name = info.get('name')
            if pkg_name: local_lookup.setdefault(pkg_name, []).append(unique_key)

        target_subdir = 'dependency'

        for root, dirs, files in os.walk(manifest_directory):
            if os.path.basename(root).lower() != target_subdir:
                dirs[:] = [d for d in dirs if d.lower() == target_subdir]

            is_root = (root == manifest_directory)
            for file in files:
                should_process = (is_root and file in args.target_manifests) or (
                        not is_root and file.endswith('.manifest'))
                if should_process:
                    manifest_path = os.path.join(root, file)
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            current_pkg_context_tuple = None
                            for line in f:
                                if '#' in line: line = line.split('#', 1)[0]
                                if not line: continue
                                line = line.strip().replace("IGNORE_IN_DEPENDENCY", "").strip()
                                if not line or line.startswith('#') or line.startswith('[') or \
                                        line.startswith(('http://', 'https://')) or line.endswith('.git'):
                                    continue

                                if line.lower().startswith(('copy ', 'move ')):
                                    if current_pkg_context_tuple:
                                        package_operations.setdefault(current_pkg_context_tuple, []).append(line)
                                    continue

                                pkg_def = line.split(':', 1)[0] if ':' in line else line

                                if '==' in pkg_def:
                                    p_name = pkg_def.split('==')[0].strip()
                                    p_ver = pkg_def.split('==')[1].strip()
                                else:
                                    p_name = pkg_def.strip()
                                    p_ver = None

                                current_pkg_context_tuple = (p_name, p_ver)

                                if ':' in line:
                                    cmd_part = line.split(':', 1)[1].strip()
                                    if cmd_part:
                                        package_operations.setdefault(current_pkg_context_tuple, []).append(cmd_part)
                    except Exception as e:
                        print(f"Error reading {manifest_path}: {e}")

        local_has_command_set = set(package_operations.keys())

        for (pkg_name, pkg_version), operations in package_operations.items():
            if not operations: continue

            real_unique_key = find_real_package_key(pkg_name, pkg_version, local_lookup, local_packages)

            if real_unique_key:
                base_source_dir = local_packages[real_unique_key]['full_path']
                for operation in operations:
                    match = re.match(r'(?P<command>\w+)\s+(?P<source>.+?)\s+to\s+(?P<destination>[^\s]+)', operation)
                    if not match: continue
                    command, source, dest = match.group('command'), match.group('source'), match.group('destination')
                    abs_dest = os.path.join(manifest_directory, dest) if dest != './' else manifest_directory
                    os.makedirs(abs_dest, exist_ok=True)
                    full_source_pattern = os.path.join(base_source_dir, source)
                    items = glob.glob(full_source_pattern)
                    if not items:
                        print(f"Warning for '{pkg_name}': No items matching '{full_source_pattern}'")
                        continue
                    print(f"Executing {pkg_name}: {command} {source} -> {dest}")
                    for item in items:
                        try:
                            if command == "copy":
                                if os.path.isfile(item):
                                    shutil.copy2(item, abs_dest)
                                elif os.path.isdir(item):
                                    shutil.copytree(item, os.path.join(abs_dest, os.path.basename(item)),
                                                    dirs_exist_ok=True)
                            elif command == "move":
                                shutil.move(item, abs_dest)
                        except Exception as e:
                            print(f"  Error: {e}")
            else:
                ver_msg = f"@{pkg_version}" if pkg_version else ""
                print(
                    Fore.YELLOW + f"Warning: Package '{pkg_name}{ver_msg}' source directory not found locally." + Style.RESET_ALL)

    finally:
        os.chdir(original_directory)

    return local_has_command_set


def import_cmake(sftp, lean_remote_path):
    remote_cmake_path = f"{lean_remote_path}/import.cmake"
    local_cmake_path = os.path.join(lean_local_path, "import.cmake")

    try:
        print("The file import.cmake is being synchronized....")
        sftp.get(remote_cmake_path, local_cmake_path)
        print(
            Fore.GREEN + f"import.cmake The file has been successfully synchronized to: {local_cmake_path}" + Style.RESET_ALL)
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Unable to synchronize the import.cmake file. Reason: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "Will continue to carry out other tasks..." + Style.RESET_ALL)

    new_filename = "gits-usage-readme.md"
    remote_new_file_path = f"{lean_remote_path}/{new_filename}"
    local_new_file_path = os.path.join(os.getcwd(), new_filename)

    try:
        print(f"The file {new_filename} is being synchronized....")
        sftp.get(remote_new_file_path, local_new_file_path)
        print(
            Fore.GREEN + f"{new_filename} The file has been successfully synchronized to: {local_new_file_path}" + Style.RESET_ALL)
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Unable to synchronize the {new_filename} file. Reason: {e}" + Style.RESET_ALL)


def write_manifest(manifest_name, spec):
    if not spec:
        return False

    current_work_dir = os.getcwd()
    full_file_path = os.path.abspath(os.path.join(current_work_dir, manifest_name))

    print(f"Checking manifest file at: {full_file_path}")

    server_packages_names = set()
    lean_remote_path = match_lean_remote()

    if lean_remote_path:
        try:
            sftp = get_sftp_session()
            if not sftp: return False
            server_dict = get_server_packages(sftp, lean_remote_path)
            server_packages_names = set(server_dict.keys())

        except Exception as e:
            print(Fore.RED + f"Warning: Failed to connect to server for verification: {e}" + Style.RESET_ALL)
            print("Aborting write operation to prevent errors.")
            return False
    else:
        print(Fore.RED + "Error: Could not determine remote path." + Style.RESET_ALL)
        return False

    detected_vs_tag = get_vs_version()

    lines = []
    existing_lines_set = set()

    if os.path.exists(full_file_path):
        try:
            with open(full_file_path, 'r', encoding='utf-8') as f:
                raw_lines = f.read().splitlines()
                for line in raw_lines:
                    line = line.strip()
                    if not line: continue
                    lines.append(line)
                    clean_content = line
                    if '#' in line:
                        clean_content = line.split('#', 1)[0]
                    clean_content = clean_content.strip()

                    if clean_content:
                        existing_lines_set.add(clean_content)
        except Exception as e:
            print(f"Warning: Could not read existing file: {e}")

    has_tag = False
    if lines:
        first_line_clean = lines[0]
        if '#' in first_line_clean:
            first_line_clean = first_line_clean.split('#', 1)[0]
        first_line_clean = first_line_clean.strip()
        # 【正则修改】匹配 [VS2019] 或 [GCC12.3.0]
        if re.match(r'^\[(VS\d+|GCC[\d\.]+)\]$', first_line_clean, re.IGNORECASE):
            has_tag = True
            print(f"Found existing compiler tag: {lines[0]}")
        else:
            print(f"No compiler tag found. Will prepend {detected_vs_tag}.")

    if not has_tag:
        lines.insert(0, detected_vs_tag)
        existing_lines_set.add(detected_vs_tag)

    packages_to_write = []
    for pkg in spec:
        clean_pkg = pkg.strip()
        if not clean_pkg: continue

        pkg_name_only = clean_pkg.split('==')[0].strip()

        if pkg_name_only not in server_packages_names:
            print(
                Fore.RED + f"Package '{pkg_name_only}' NOT FOUND on remote server. Skipping write." + Style.RESET_ALL)
            continue
        existing_pkg_names = set()
        for l in existing_lines_set:
            if not l.startswith('[') and not l.startswith('#'):
                existing_pkg_names.add(l.split('==')[0].strip().split(':')[0].strip())

        if pkg_name_only in existing_pkg_names:
            print(f"Package '{pkg_name_only}' is already in the manifest, skipping.")
            continue

        packages_to_write.append(clean_pkg)
        lines.append(clean_pkg)
        existing_lines_set.add(clean_pkg)
        existing_pkg_names.add(pkg_name_only)

    if not packages_to_write:
        if has_tag:
            print("No valid new packages to write.")
        return True

    print(f"Writing {len(packages_to_write)} new packages to {manifest_name}...")

    try:
        with open(full_file_path, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(f"{line}\n")
        print("Write complete.")
        return True
    except Exception as e:
        print(f"Error writing manifest: {e}")
        return False


def resolve_lean_args(args):
    args.target_manifests = []
    if args.manifest_filename:
        args.manifest_filename = os.path.normpath(args.manifest_filename)

    compiler_arg = getattr(args, 'compiler', None)

    if not args.obj_name and not args.manifest_filename and not args.spec and not compiler_arg:
        sys_vs_tag = get_vs_version()
        if sys_vs_tag and sys_vs_tag.startswith('[') and sys_vs_tag.endswith(']'):
            detected_compiler = sys_vs_tag[1:-1]
            print(
                Fore.CYAN + f"No parameters provided. Auto-detected system compiler: {detected_compiler}" + Style.RESET_ALL)
            compiler_arg = detected_compiler
            args.compiler = detected_compiler
        else:
            print(
                Fore.RED + "Unspecified parameters. Please provide --manifest, --obj-name, --spec, or --compiler." + Style.RESET_ALL)
            return False

    if args.spec:
        if compiler_arg:
            print(
                Fore.YELLOW + "Warning: --compiler is ignored because --spec implies a specific file operation." + Style.RESET_ALL)

        if not args.obj_name and not args.manifest_filename:
            args.obj_name = ['default']
            args.manifest_filename = 'default.manifest'
        elif args.obj_name and not args.manifest_filename:
            args.manifest_filename = f'{args.obj_name[0]}.manifest'

        if not write_manifest(args.manifest_filename, args.spec):
            return False

        args.spec = None
        args.target_manifests = [args.manifest_filename]
        return True

    if args.manifest_filename:
        args.target_manifests = [args.manifest_filename]
        if not args.obj_name:
            base_name = os.path.splitext(os.path.basename(args.manifest_filename))[0]
            args.obj_name = [base_name]
        return True

    if args.obj_name and len(args.obj_name) == 1:
        candidate = f'{args.obj_name[0]}.manifest'
        if os.path.exists(candidate):
            args.manifest_filename = candidate
            args.target_manifests = [candidate]
            return True
        else:
            if not compiler_arg:
                print(Fore.RED + f"{candidate} does not exist. Exiting..." + Style.RESET_ALL)
                return False

    if compiler_arg:
        target_compiler = compiler_arg.upper()
        print(f"Scanning root directory for manifests matching [{target_compiler}]...")

        for file in os.listdir('.'):
            if file.endswith('.manifest') and os.path.isfile(file):
                tag = get_file_compiler_tag(file)
                if tag == target_compiler:
                    args.target_manifests.append(file)

        if not args.target_manifests:
            print(
                Fore.YELLOW + f"Warning: No manifest files found with tag [{target_compiler}] in root directory." + Style.RESET_ALL)
            return False

        args.obj_name = [os.path.splitext(f)[0] for f in args.target_manifests]

        print(f"Found {len(args.target_manifests)} matching manifests: {args.target_manifests}")
        print(f"Mapped to objects: {args.obj_name}")
        return True

    return False


def get_file_compiler_tag(file_path):
    try:
        if not os.path.isfile(file_path):
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if first_line.startswith('\ufeff'):
                first_line = first_line[1:]

            # 【正则修改】匹配 [VS2019] 或 [GCC12.3.0]
            match = re.match(r'^\[(VS\d+|GCC[\d\.]+)\]$', first_line, re.IGNORECASE)
            if match:
                return match.group(1).upper()
    except Exception:
        pass
    return None


# --- 【核心修改】环境变量配置 (Linux 适配) ---
def configure_env_vars(final_reqs, remote_cmds, local_cmds_set):
    # 跨平台支持

    excluded_pkgs = set()
    if remote_cmds:
        excluded_pkgs.update(remote_cmds.keys())
    if local_cmds_set:
        excluded_pkgs.update(local_cmds_set)

    local_packages = get_local_packages()
    local_lookup = {}
    for key, info in local_packages.items():
        if info.get('name'): local_lookup.setdefault(info['name'], []).append(key)

    has_action = False

    for req in final_reqs:
        pkg_name = req['name']
        pkg_version = req['version']

        if (pkg_name, pkg_version) in excluded_pkgs:
            continue

        real_unique_key = find_real_package_key(pkg_name, pkg_version, local_lookup, local_packages)

        if not real_unique_key: continue

        bin_path = os.path.join(local_packages[real_unique_key]['full_path'], "bin")

        if os.path.isdir(bin_path):
            if not has_action:
                print("Configuring environment variables...")
                has_action = True

            # 使用新的跨平台添加路径函数
            if add_to_system_path_env(bin_path):
                print(Fore.GREEN + f"Added to PATH: {bin_path}" + Style.RESET_ALL)

    if has_action:
        print("Environment configuration check done.")


def update_lean(args, repo_path):
    if not resolve_lean_args(args):
        return False

    lean_remote_path = match_lean_remote()
    if lean_remote_path is None:
        print(
            Fore.RED + "Error: Could not determine a valid remote path for the current OS. Aborting update." + Style.RESET_ALL)
        return False
    try:
        sftp = get_sftp_session()
        if not sftp: return False
        import_cmake(sftp, lean_remote_path)

        print("Checking local lean packages:")
        final_reqs, remote_cmds = get_lean_mainfest_packages(
            args, repo_path, sftp=sftp, lean_remote_path=lean_remote_path
        )
        print(
            f"Found local packages: {len(get_local_packages())} \nremote packages: {len(get_server_packages(sftp, lean_remote_path))} \nproject need packages: {len(final_reqs)} ")
        compare_packages(args, sftp, lean_remote_path)
        print(f"{len(unresolved_packages)} unresolved packages (NOT FOUND on server): ", end="")
        if len(unresolved_packages) != 0:
            print(Fore.RED + "[" + ", ".join(unresolved_packages) + "]" + Style.RESET_ALL)
        else:
            print("None!")
        print(f"{len(missing_packages)} missing packages : ", end="")
        if len(missing_packages) != 0:
            for i, pkg in enumerate(missing_packages):
                if i > 0:
                    print(",", end='')
                print(f"[{pkg}]", end='')

            print()
        else:
            print("None!")
        print(f"{len(need_update_packages)} packages need to update: ", end="")
        if len(need_update_packages) != 0:
            for i, pkg in enumerate(need_update_packages):
                if i > 0:
                    print(",", end='')
                print(f"[{pkg}]", end='')

            print()
        else:
            print("None!")
        success = 0
        fetch_failed = 0
        unzip_faild = 0
        fetch_failed_name = []
        unzip_faild_name = []
        if len(missing_packages_) != 0:
            print("Fetching missing lean packages:")
            for package_path in missing_packages_:
                num, name = download_package(sftp, package_path)
                if num == 1:
                    fetch_failed += 1
                    fetch_failed_name.append(name)
                elif num == 2:
                    success += 1
                elif num == 3:
                    unzip_faild += 1
                    unzip_faild_name.append(name)
        if len(need_update_packages_) != 0:
            print("Updating lean packages:")
            for package_path in need_update_packages_:
                num, name = download_package(sftp, package_path)
                if num == 1:
                    fetch_failed += 1
                    fetch_failed_name.append(name)
                elif num == 2:
                    success += 1
                elif num == 3:
                    unzip_faild += 1
                    unzip_faild_name.append(name)
        print("Lean fetch process finish~")
        print(f"Total lean packages num: {success + fetch_failed + unzip_faild}")
        print(f"Succeed packages num: {success}")
        print(f"Fetch failed packages:  ", end="")
        if len(fetch_failed_name) != 0:
            for i, pkg in enumerate(fetch_failed_name):
                if i > 0:
                    print(",", end='')
                print(f"[{pkg}]", end='')

            print()
        else:
            print("None!")
        print(f"Unzip failed packages:  ", end="")
        if len(unzip_faild_name) != 0:
            for i, pkg in enumerate(unzip_faild_name):
                if i > 0:
                    print(",", end='')
                print(f"[{pkg}]", end='')

            print()
        else:
            print("None!")
        print("Your local lean packages are all up to date with remote lean server.")
        workspace_directory = os.path.join(repo_path, "workspace")
        print("Starting copy lean dll to workspace...")
        local_manifest_set = process_manifests(args, repo_path)
        execute_remote_copy(repo_path, remote_cmds)
        configure_env_vars(final_reqs, remote_cmds, local_manifest_set)
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check the username and password.")
        return False
    except Exception as e:
        print(f" {e}")
        return False
    return True


def new_obj_name(args):
    if not resolve_lean_args(args): return

    for current_obj in args.obj_name:
        print(f"\n[new-obj] Creating Object: {Fore.CYAN}{current_obj}{Style.RESET_ALL}")

        cmake_list = f'cmake/{current_obj}'
        command = ['gis', 'new-obj', cmake_list]

        if args.dll:
            command.append('--dll')
        elif args.lib:
            command.append('--lib')
        else:
            command.append('--exe')

        print(f"Running command: {' '.join(command)}")
        # 【修改点】 动态编码
        result = subprocess.run(command, text=True, encoding=SYS_ENCODING, check=True)


def import_dep_lean(args):
    if not resolve_lean_args(args): return
    lean_remote_path = match_lean_remote()
    if lean_remote_path is None:
        print(Fore.RED + "Error: Could not determine remote path." + Style.RESET_ALL)
        return

    try:
        sftp = get_sftp_session()
        if not sftp: return
    except Exception as e:
        print(f"Error connecting: {e}")
        return

    local_packages = get_local_packages()
    local_lookup = {}
    for unique_key, info in local_packages.items():
        if info.get('name'):
            local_lookup.setdefault(info['name'], []).append(unique_key)

    if len(args.target_manifests) != len(args.obj_name):
        return

    for current_manifest, current_obj in zip(args.target_manifests, args.obj_name):
        print(f"\n[import] Processing Object: {Fore.CYAN}{current_obj}{Style.RESET_ALL} (from {current_manifest})")

        original_targets = args.target_manifests
        args.target_manifests = [current_manifest]

        try:
            current_reqs, _ = get_lean_mainfest_packages(
                args, os.getcwd(), root_only=True, sftp=sftp, lean_remote_path=lean_remote_path
            )
            current_git_deps = get_lean_mainfest_depurl(args, os.getcwd(), root_only=True)
        except Exception as e:
            print(Fore.RED + f"Error parsing manifest: {e}" + Style.RESET_ALL)
            args.target_manifests = original_targets
            continue

        args.target_manifests = original_targets

        if not current_reqs and not current_git_deps:
            print(f"No dependencies found in {current_manifest}.")

        for package_info in current_reqs:
            pkg_name = package_info['name']
            req_version = package_info['version']

            real_key = find_real_package_key(pkg_name, req_version, local_lookup, local_packages)

            folder_name_to_import = None
            if real_key:
                folder_name_to_import = os.path.basename(local_packages[real_key]['full_path'])

            if folder_name_to_import:
                cmake_list = f'cmake/{current_obj}'
                command = ['gis', 'import', folder_name_to_import, '--to', cmake_list]
                print(f"Running command: {' '.join(command)}")
                try:
                    # 【修改点】 动态编码
                    subprocess.run(command, text=True, encoding=SYS_ENCODING, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error importing {folder_name_to_import}: {e}")
            else:
                ver_msg = f"@{req_version}" if req_version else ""
                print(
                    Fore.YELLOW + f"Warning: Package '{pkg_name}{ver_msg}' not found locally. Skipping." + Style.RESET_ALL)

        for dep in current_git_deps:
            clean_dep = dep.split('==')[0]
            filename_with_ext = os.path.basename(clean_dep)
            if filename_with_ext.endswith('.git'):
                repo_name = filename_with_ext[:-4]
            else:
                repo_name = os.path.splitext(filename_with_ext)[0]

            local_dep_path = f"dependency/{repo_name}"
            cmake_list = f'cmake/{current_obj}'
            command = ['gis', 'import', local_dep_path, '--to', cmake_list]
            print(f"Running command: {' '.join(command)}")
            try:
                # 【修改点】 动态编码
                subprocess.run(command, text=True, encoding=SYS_ENCODING, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error importing dependency {repo_name}: {e}")


def check_obj(args):
    if not resolve_lean_args(args): return

    for current_obj in args.obj_name:
        print(f"\n[check-obj] Processing: {Fore.CYAN}{current_obj}{Style.RESET_ALL}")

        command = ['gis', 'check', '.', '--import']
        print(f"Running command: {' '.join(command)}")

        # 【修改点】 动态编码
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding=SYS_ENCODING)

        output_lines = result.stdout.splitlines()
        add_targets = []

        for i, line in enumerate(output_lines):
            clean_line = line.strip()
            if clean_line.startswith("gits add"):
                keyword = '--obj '
                keyword_index = clean_line.find(keyword)
                if keyword_index != -1:
                    targets_string = clean_line[keyword_index + len(keyword):]
                    targets_list = targets_string.split()
                    add_targets.extend(targets_list)

        if current_obj not in add_targets:
            cmake_list = f'cmake/{current_obj}'
            command = ['gis', 'export', cmake_list, '--obj-name', current_obj]
            print(f"Running command: {' '.join(command)}")
            subprocess.run(command, text=True, encoding=SYS_ENCODING, check=True)

        object_name = f'{os.path.basename(os.getcwd())}_{current_obj}'
        command = ['gis', 'add', '.', '--obj-name', object_name]
        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, text=True, encoding=SYS_ENCODING, check=True)


def update_lean_specific(args):
    if not resolve_lean_args(args):
        return

    lean_remote_path = match_lean_remote()
    if lean_remote_path is None:
        print(Fore.RED + "Error: Could not determine a valid remote path. Aborting." + Style.RESET_ALL)
        return

    try:
        sftp = get_sftp_session()
        if not sftp: return False
        import_cmake(sftp, lean_remote_path)

        specific_lean = args.specific
        if getattr(args, 'compiler', None):
            target_compiler = args.compiler.upper()
        else:
            target_file = args.target_manifests[0] if args.target_manifests else args.manifest_filename
            target_compiler = get_project_compiler(os.getcwd(), target_file)

        req_pkg_name = specific_lean
        req_version_str = None

        if '==' in specific_lean:
            parts = specific_lean.split('==', 1)
            req_pkg_name = parts[0].strip()
            req_version_str = parts[1].strip()

        server_packages = get_server_packages(sftp, lean_remote_path)

        if req_pkg_name not in server_packages:
            print(Fore.RED + f"Error: Package '{req_pkg_name}' not found on server." + Style.RESET_ALL)
            return

        all_versions = server_packages[req_pkg_name]
        target_info = None

        if req_version_str:
            try:
                req_version_obj = parse_version(req_version_str)

                target_info = next((v for v in all_versions if
                                    v['version'] == req_version_obj and v['compiler'] == target_compiler), None)

                if not target_info:
                    target_info = next((v for v in all_versions if v['version'] == req_version_obj), None)
                    if target_info:
                        print(
                            Fore.YELLOW + f"Warning: Found version {req_version_str} in {target_info['compiler']} (Target is {target_compiler}). Using it." + Style.RESET_ALL)

            except InvalidVersion:
                print(Fore.RED + f"Error: Invalid version format '{req_version_str}'" + Style.RESET_ALL)
                return
        else:
            def find_best_in_list(ver_list):
                stable = [v for v in ver_list if v['location'] == 'stable']
                common = [v for v in ver_list if v['location'] == 'common']
                if stable: return max(stable, key=lambda v: v['version'])
                if common: return max(common, key=lambda v: v['version'])
                return None

            target_compiler_versions = [v for v in all_versions if v['compiler'] == target_compiler]
            if target_compiler_versions:
                target_info = find_best_in_list(target_compiler_versions)

            if not target_info:
                print(
                    Fore.YELLOW + f"Warning: No version found for '{req_pkg_name}' in {target_compiler}. Searching all compilers..." + Style.RESET_ALL)
                target_info = find_best_in_list(all_versions)
        if not target_info:
            ver_msg = f"version {req_version_str}" if req_version_str else "any version"
            print(Fore.RED + f"Error: Could not find {ver_msg} for {req_pkg_name}." + Style.RESET_ALL)
            return

        full_remote_path = target_info['full_path']
        version_str = target_info['version_str']
        found_compiler = target_info['compiler']

        local_packages = get_local_packages()
        target_key = f"{req_pkg_name}@{version_str}@{found_compiler}"

        should_download = False
        if target_key not in local_packages:
            print(f"Status: Missing locally.")
            should_download = True
        else:
            local_info = local_packages[target_key]
            if target_info['time'] > local_info['time']:
                print(f"Status: Update available (Server is newer).")
                should_download = True
            else:
                print(Fore.GREEN + f"Status: Local version is up to date." + Style.RESET_ALL)

        if should_download:
            download_package(sftp, full_remote_path)

    except paramiko.AuthenticationException:
        print("Authentication failed. Please check the username and password.")
    except Exception as e:
        print(f"An error occurred: {e}")


def status_lean_local(args, repo_path):
    if not resolve_lean_args(args):
        return

    lean_remote_path = match_lean_remote()
    if lean_remote_path is None:
        return

    original_directory = os.getcwd()

    try:
        sftp = get_sftp_session()
        if not sftp: return False
        print("Checking local lean packages status...")

        final_reqs, remote_copy_cmds = get_lean_mainfest_packages(
            args, repo_path, sftp=sftp, lean_remote_path=lean_remote_path
        )

        compare_packages(args, sftp, lean_remote_path)

        print(f"{len(unresolved_packages)} unresolved packages: ", end="")
        if unresolved_packages:
            print(Fore.RED + str(unresolved_packages) + Style.RESET_ALL)
        else:
            print("None!")

        print(f"{len(missing_packages)} missing packages: ", end="")
        if missing_packages:
            print(missing_packages)
        else:
            print("None!")

        print(f"{len(need_update_packages)} packages need to update: ", end="")
        if need_update_packages:
            print(need_update_packages)
        else:
            print("None!")

        print("Checking workspace file synchronization...")

        os.chdir(repo_path)
        package_operations = {}

        target_subdir = 'dependency'

        for root, dirs, files in os.walk(repo_path):
            if os.path.basename(root).lower() != target_subdir:
                dirs[:] = [d for d in dirs if d.lower() == target_subdir]

            is_root = (root == repo_path)
            for file in files:
                should_process = (is_root and file in args.target_manifests) or (
                        not is_root and file.endswith('.manifest'))

                if should_process:
                    manifest_path = os.path.join(root, file)
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            current_pkg_context_tuple = None
                            for line in f:
                                if '#' in line: line = line.split('#', 1)[0]
                                if not line: continue
                                line = line.strip().replace("IGNORE_IN_DEPENDENCY", "").strip()
                                if not line or line.startswith('#') or line.startswith('[') or \
                                        line.startswith(('http://', 'https://')) or line.endswith('.git'):
                                    continue
                                if line.lower().startswith(('copy ', 'move ')):
                                    if current_pkg_context_tuple:
                                        package_operations.setdefault(current_pkg_context_tuple, []).append(line)
                                    continue

                                pkg_def = line.split(':', 1)[0] if ':' in line else line
                                if '==' in pkg_def:
                                    p_name = pkg_def.split('==')[0].strip()
                                    p_ver = pkg_def.split('==')[1].strip()
                                else:
                                    p_name = pkg_def.strip()
                                    p_ver = None
                                current_pkg_context_tuple = (p_name, p_ver)

                                if ':' in line:
                                    cmd_part = line.split(':', 1)[1].strip()
                                    if cmd_part:
                                        package_operations.setdefault(current_pkg_context_tuple, []).append(cmd_part)
                    except Exception as e:
                        print(f"Error reading {manifest_path}: {e}")

        if remote_copy_cmds:
            for key_tuple, cmds in remote_copy_cmds.items():
                for cmd in cmds:
                    package_operations.setdefault(key_tuple, []).append(cmd)

        local_packages = get_local_packages()
        local_lookup = {}
        for unique_key, info in local_packages.items():
            if info.get('name'): local_lookup.setdefault(info['name'], []).append(unique_key)

        for (pkg_name, pkg_version), operations in package_operations.items():
            if not operations: continue

            real_unique_key = find_real_package_key(pkg_name, pkg_version, local_lookup, local_packages)

            if real_unique_key:
                base_source_dir = local_packages[real_unique_key]['full_path']
                for operation in operations:
                    match = re.match(r'(?P<command>\w+)\s+(?P<source>.+?)\s+to\s+(?P<destination>[^\s]+)', operation)
                    if not match: continue
                    command, source, dest = match.group('command'), match.group('source'), match.group('destination')
                    abs_dest_dir = os.path.join(repo_path, dest) if dest != './' else repo_path
                    full_source_pattern = os.path.join(base_source_dir, source)
                    source_items = glob.glob(full_source_pattern)

                    if not source_items:
                        ver_msg = f"@{pkg_version}" if pkg_version else ""
                        print(f"Warning for '{pkg_name}{ver_msg}': Source pattern '{source}' matches nothing")
                        continue

                    missing_files = []
                    for item in source_items:
                        item_name = os.path.basename(item)
                        expected_dest_path = os.path.join(abs_dest_dir, item_name)
                        if not os.path.exists(expected_dest_path):
                            rel_missing = os.path.relpath(expected_dest_path, repo_path)
                            missing_files.append(rel_missing)

                    if missing_files:
                        print(
                            Fore.RED + f"{pkg_name}: {operation} missing: {', '.join(missing_files)}" + Style.RESET_ALL)
                    else:
                        print(Fore.GREEN + f"{pkg_name}: {operation} OK!" + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + f"Warning: Cannot check files for '{pkg_name}'" + Style.RESET_ALL)

        # 【修改点5】 环境变量检查 (适配 Linux)
        print("Checking environment variables for non-command packages...")
        has_command_set = set(package_operations.keys())

        # 跨平台获取当前 PATH
        reg_path_str = get_system_path_env()
        # 根据系统使用 ; 或 : 分割
        sep = ';' if IS_WINDOWS else ':'
        reg_path_set = {os.path.normpath(p).lower() for p in reg_path_str.split(sep) if p.strip()}

        env_missing_count = 0

        for req in final_reqs:
            pkg_name = req['name']
            pkg_version = req['version']

            if (pkg_name, pkg_version) in has_command_set: continue

            real_unique_key = find_real_package_key(pkg_name, pkg_version, local_lookup, local_packages)
            if not real_unique_key: continue

            bin_path = os.path.join(local_packages[real_unique_key]['full_path'], "bin")

            if os.path.isdir(bin_path):
                norm_bin = os.path.normpath(bin_path).lower()
                if norm_bin in reg_path_set:
                    print(Fore.GREEN + f"[{pkg_name}] Environment variable OK." + Style.RESET_ALL)
                else:
                    print(Fore.RED + f"[{pkg_name}] Missing in PATH: {bin_path}" + Style.RESET_ALL)
                    env_missing_count += 1

        if env_missing_count > 0:
            print(
                Fore.YELLOW + f"Tip: Run 'gis update' to automatically fix {env_missing_count} missing environment variables." + Style.RESET_ALL)
        else:
            print("All environment variables are correct.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        os.chdir(original_directory)


def status_lean_remote():
    lean_remote_path = match_lean_remote()
    if lean_remote_path is None:
        print(
            Fore.RED + "Error: Could not determine a valid remote path for the current OS. Aborting update." + Style.RESET_ALL)
        return

    try:
        sftp = get_sftp_session()
        if not sftp: return False
        import_cmake(sftp, lean_remote_path)

        server_packages = get_server_packages(sftp, lean_remote_path)

        print(f"{'Package':<25} {'Version':<15} {'Location':<10} {'Date'}")
        print("-" * 75)

        for name, versions_list in server_packages.items():
            for info in versions_list:
                version_str = str(info['version'])
                location = info['location']
                date_str = str(info['time'])

                print(f"{name:<25} {version_str:<15} {location:<10} {date_str}")

    except paramiko.AuthenticationException:
        print("Authentication failed. Please check the username and password.")
    except Exception as e:
        print(f"An error occurred: {e}")