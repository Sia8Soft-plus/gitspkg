import platform
import shutil
import subprocess
import tempfile
import sys
import os
import re
import paramiko

# --- 【关键修改】仅在 Windows 下导入特定库 ---
if os.name == 'nt':
    try:
        import winreg
        import ctypes
    except ImportError:
        pass  # 开发环境下非 Windows 系统可能没有这些库

# Linux 环境变量文件 (系统级)
LINUX_ENV_FILE = "/etc/profile.d/gis_env.sh"


def _linux_write_env(var_name, var_value):
    """Linux: 写入环境变量到 /etc/profile.d"""
    env_dir = os.path.dirname(LINUX_ENV_FILE)
    if not os.path.exists(env_dir):
        print(f"Warning: {env_dir} does not exist. Environment variable may not persist globally.")
        return

    lines = []
    if os.path.exists(LINUX_ENV_FILE):
        try:
            with open(LINUX_ENV_FILE, 'r') as f:
                lines = f.readlines()
        except:
            lines = []

    # 移除旧的定义，避免重复
    lines = [line for line in lines if not line.strip().startswith(f"export {var_name}=")]
    lines.append(f'export {var_name}="{var_value}"\n')

    try:
        with open(LINUX_ENV_FILE, 'w') as f:
            f.writelines(lines)
        os.chmod(LINUX_ENV_FILE, 0o644)
        print(f"Environment variable {var_name} added to {LINUX_ENV_FILE}")
    except PermissionError:
        print(f"Permission denied: Cannot write to {LINUX_ENV_FILE}. Sudo required.")


def _linux_remove_env(var_name):
    """Linux: 移除环境变量"""
    if not os.path.exists(LINUX_ENV_FILE): return
    try:
        with open(LINUX_ENV_FILE, 'r') as f:
            lines = f.readlines()
        new_lines = [line for line in lines if not line.strip().startswith(f"export {var_name}=")]
        with open(LINUX_ENV_FILE, 'w') as f:
            f.writelines(new_lines)
    except:
        pass


def _linux_get_env(var_name):
    """Linux: 读取环境变量"""
    # 优先读取当前会话的环境变量
    val = os.environ.get(var_name)
    if val: return val

    # 其次读取配置文件
    if not os.path.exists(LINUX_ENV_FILE): return False
    try:
        with open(LINUX_ENV_FILE, 'r') as f:
            content = f.read()
        match = re.search(f'export {var_name}="([^"]+)"', content)
        if match: return match.group(1)
    except:
        pass
    return False


def show_success_ascii():
    print("-" * 25)
    print("[GIS POWERED BY SIA8-SOFT]")
    print("-" * 25)
    print("Install gis successfully!")
    if os.name != 'nt':
        print("Note: You can run 'gis' from any terminal now.")
        print("Note: Run 'source /etc/profile.d/gis_env.sh' to apply environment variables immediately.")


def is_admin():
    """检查权限"""
    if os.name == 'nt':
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        # Linux 检查 Root (euid 0)
        return os.geteuid() == 0


def sys_env_is_exist(var_name):
    if os.name == 'nt':
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
                0, winreg.KEY_READ
            )
            value, _ = winreg.QueryValueEx(key, var_name)
            winreg.CloseKey(key)
            return value
        except FileNotFoundError:
            return False
        except Exception as e:
            # 忽略一些读取错误
            return False
    else:
        return _linux_get_env(var_name)


def set_system_env(var_name, var_value):
    """设置系统级环境变量"""
    if not is_admin():
        print("Administrator/Root privileges required.")
        if os.name == 'nt':
            try:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                sys.exit()
            except:
                pass
        return

    if os.name == 'nt':
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
                0, winreg.KEY_ALL_ACCESS
            )
            winreg.SetValueEx(key, var_name, 0, winreg.REG_EXPAND_SZ, var_value)
            winreg.CloseKey(key)
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, 'Environment', 0, 1000, None)
            print(f"System variable {var_name} added with value {var_value}.")
        except Exception as e:
            print(f"Operation failed: {e}")
    else:
        _linux_write_env(var_name, var_value)


def add_system_path(path_value):
    """将路径添加到系统级 PATH 变量 (Linux下创建软链接)"""
    if not is_admin():
        if os.name == 'nt':
            try:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                sys.exit()
            except:
                pass
        else:
            print("Root privileges required.")
            return

    if os.name == 'nt':
        # Windows 逻辑
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
                0,
                winreg.KEY_ALL_ACCESS
            )
            current_path, _ = winreg.QueryValueEx(key, 'Path')
            # 简单的防重复检查（忽略大小写）
            if path_value.lower() not in current_path.lower().split(';'):
                new_path = f"{current_path};{path_value}" if current_path else path_value
                winreg.SetValueEx(key, 'Path', 0, winreg.REG_EXPAND_SZ, new_path)
                winreg.CloseKey(key)
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, 'Environment', 0, 1000, None)
                print(f"add {path_value} to the system PATH environment variable.")
            show_success_ascii()
        except Exception as e:
            print(f"Failed to update PATH: {e}")
    else:
        # Linux 逻辑：创建软链接到 /usr/local/bin
        # 假设打包后的可执行文件名为 gis (无后缀)
        src_bin = os.path.join(path_value, "gis")
        if not os.path.exists(src_bin):
            # 如果是开发环境 (未冻结)，可能指向 python 解释器，这里仅做容错
            if getattr(sys, 'frozen', False):
                src_bin = sys.executable
            else:
                # 源码运行模式下，不做软链，只提示
                print("Dev mode detected: Skipping symlink creation.")
                return

        target_link = "/usr/local/bin/gis"

        if os.path.exists(src_bin):
            try:
                if os.path.lexists(target_link): os.remove(target_link)
                os.symlink(src_bin, target_link)
                # 赋予执行权限
                os.chmod(src_bin, 0o755)
                show_success_ascii()
            except Exception as e:
                print(f"Link failed: {e}")
        else:
            print(f"Error: Executable not found at {src_bin}")


def delete_system_env_variable(var_name):
    """删除系统级环境变量"""
    if not is_admin():
        if os.name == 'nt':
            try:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                sys.exit()
            except:
                pass
        return

    if os.name == 'nt':
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
                0,
                winreg.KEY_ALL_ACCESS
            )
            winreg.DeleteValue(key, var_name)
            winreg.CloseKey(key)
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, 'Environment', 0, 1000, None)
            print(f"System variable deleted successfully: {var_name}")
            return True
        except FileNotFoundError:
            print(f"Environment variable {var_name} does not exist.")
            return False
        except Exception as e:
            print(f"Error while deleting environment variable: {e}")
            return False
    else:
        _linux_remove_env(var_name)
        print(f"Variable {var_name} removed.")
        return True


def delete_from_path(variable_to_remove):
    """从 PATH 环境变量中删除指定的路径"""
    if os.name == 'nt':
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
                0,
                winreg.KEY_ALL_ACCESS
            )
            path_value, _ = winreg.QueryValueEx(key, "Path")
            paths = path_value.split(';')
            paths = [p for p in paths if p.strip() != variable_to_remove]
            new_path_value = ';'.join(paths)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path_value)
            winreg.CloseKey(key)
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, 'Environment', 0, 1000, None)
            print(f"Successfully removed from PATH: {variable_to_remove}")
            return True
        except Exception as e:
            print(f"An error occurred while updating PATH: {e}")
            return False
    else:
        # Linux: 删除软链接
        target = "/usr/local/bin/gis"
        if os.path.lexists(target):
            try:
                os.remove(target)
                print("Symlink removed.")
            except:
                pass
        return True


def get_system_env_variable(var_name):
    return sys_env_is_exist(var_name)


def check_git_installed():
    try:
        result = subprocess.run(['git', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_cmake_installed():
    try:
        result = subprocess.run(['cmake', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_refreshed_env_path():
    """Windows Only"""
    if os.name != 'nt': return ""
    try:
        user_key_path = r"Environment"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_key_path, 0, winreg.KEY_READ) as key:
            try:
                user_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                user_path = ""
        system_key_path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, system_key_path, 0, winreg.KEY_READ) as key:
            system_path, _ = winreg.QueryValueEx(key, "Path")
        return user_path + os.pathsep + system_path
    except Exception as e:
        print(f"Error reading registry to refresh env: {e}")
        return os.environ.get("Path", "")


def download_file(save_path):
    # 【修改点】Linux下跳过 MSI 下载
    if os.name != 'nt':
        return False

    try:
        # 创建 SSH 客户端并连接 (Windows 下载安装包)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("114.115.165.12", username="sia", password="Sia8soft")
        with ssh.open_sftp() as sftp:
            sftp.get("/home/sia/Documents/files/gits/setup/cmake-3.29.8-windows-x86_64.msi", save_path)
        return True
    except Exception as e:
        print(f"An error occurred while downloading the file:{e}")
        return False
    finally:
        ssh.close()


def execute_installation(install_git: bool, install_cmake: bool):
    if not install_git and not install_cmake:
        print("No specific software packages were designated for installation.")
        return True

    system = platform.system()

    if system == 'Windows':
        # --- Windows 逻辑保持原样 ---
        command_base = ['winget', 'install', '--accept-source-agreements', '--accept-package-agreements', '-e']
        did_install_anything = False

        if install_git:
            print("\nPrepare to install Git...")
            git_command = command_base + ['--id', 'Git.Git']
            try:
                subprocess.run(git_command, check=True, capture_output=True, text=True, encoding='utf-8')
                print("Git installation was successful.")
                did_install_anything = True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"\nGit installation failed! \nError details: {e.stderr if hasattr(e, 'stderr') else e}")
                return False

        if install_cmake:
            temp_dir = tempfile.gettempdir()
            download_dir = os.path.join(temp_dir, "gits_installer_packages")
            os.makedirs(download_dir, exist_ok=True)
            print("Prepare to install CMake...")

            try:
                cmake_msi_path = os.path.join(download_dir, "cmake-3.29.8-windows-x86_64.msi")
                if not download_file(cmake_msi_path):
                    print("Failed to download the CMake installation package!")
                    return False

                if not os.path.exists(cmake_msi_path):
                    print(f"Cannot find the CMake installation package:{cmake_msi_path}")
                    return False

                cmake_command = [
                    'msiexec', '/i', cmake_msi_path, '/qn', '/norestart', 'ADD_CMAKE_TO_PATH=System'
                ]
                subprocess.run(cmake_command, check=True, shell=True)
                print("CMake installation was successful.")
                did_install_anything = True

            except subprocess.CalledProcessError as e:
                print(f"\nCMake installation failed! Return code: {e.returncode}")
                return False
            except Exception as e:
                print(f"\nAn unknown error occurred during the CMake installation process:{e}")
                return False
            finally:
                if os.path.exists(download_dir):
                    print(f"\nCleaning up temporary files:{download_dir}")
                    shutil.rmtree(download_dir)

        if did_install_anything:
            print("\nInstallation completed. Attempting to refresh environment variables...")
            refreshed_path = get_refreshed_env_path()
            os.environ["Path"] = refreshed_path
            print("The environment variables have been refreshed in the current script.")

        return True
    elif system == 'Linux':
        # --- Linux 逻辑 ---
        print(f"Detected Linux, installing via apt-get...")
        # 容错：有些精简版 Linux 可能没有 apt-get
        if not os.path.exists("/usr/bin/apt-get"):
            print("Error: 'apt-get' not found. Auto-install only supports Debian/Ubuntu based systems.")
            print("Please install git and cmake manually using your package manager (yum, dnf, pacman, etc.).")
            return True  # 返回 True 让流程继续，交给后续检查

        packages_to_install = []
        if install_git: packages_to_install.append('git')
        if install_cmake: packages_to_install.append("cmake")

        if packages_to_install:
            print("Updating apt...")
            try:
                subprocess.run(['sudo', 'apt-get', 'update'], check=True)
                command = ['sudo', 'apt-get', 'install', '-y'] + packages_to_install
                print(f"Executing: {' '.join(command)}")
                subprocess.run(command, check=True)
                print("Packages installed.")
            except Exception as e:
                print(f"Install failed: {e}")
                return False
        return True

    else:
        print(f"System {system} not supported for auto-install.")
        return False


def check_gitconfig():
    cmds = []
    if os.name == 'nt':
        # Windows 保持 CRLF 转换
        cmds = [
            ['git', 'config', '--system', 'core.autocrlf', 'true'],
            ['git', 'config', '--system', 'core.safecrlf', 'false'],
            ['git', 'config', '--global', 'core.autocrlf', 'true'],
            ['git', 'config', '--global', 'core.safecrlf', 'false']
        ]
    else:
        # Linux 使用 input 模式 (checkout时不转, commit时转LF)
        cmds = [
            ['git', 'config', '--system', 'core.autocrlf', 'input'],
            ['git', 'config', '--global', 'core.autocrlf', 'input']
        ]

    for cmd in cmds:
        try:
            # 忽略错误（例如非 sudo 运行无法修改 system config）
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except:
            pass
    print("Gits git config applied.")