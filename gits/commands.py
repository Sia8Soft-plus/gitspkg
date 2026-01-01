import os.path as osp
import shutil
import pyfiglet
import sys
from art import text2art
import gits
from gits.lean import update_lean, update_lean_specific, status_lean_local, status_lean_remote, new_obj_name
from utils import write_to_path
from gits.config import MAIN_PATH, execute_configs, show_config
import subprocess
import os
from colorama import Fore, init, Style
from gits.dep import clone_repository, update_dependencies, status_dep, update_dependency_specific, install_dep
from gits.cmake import check_commands, check_obj
from conf import config
from utils.write_to_path import execute_installation, check_gitconfig
from utils.generate_config import gene_conf

init()


def cmds(args, remaining):
    if not before_check(args):
        return

    if args.command == 'install':
        install(args)
    elif args.command == 'uninstall':
        uninstall()
    elif args.command == 'config':
        flag = execute_configs(args)
        if not flag and remaining:
            trans_command(args, remaining)
            if remaining[0] == '--list':
                print('-' * 35)
                show_config()
    elif args.command == 'clone':
        clone(args)
    elif args.command == 'update':
        update(args)
    elif args.command == 'status':
        status(args)
    elif args.command == 'version':
        version()
    elif args.command == 'check':
        check_import(args)
    elif args.command == 'import':
        import_dep_lean(args)
    elif args.command == 'new-obj':
        new_obj(args)
    elif args.command == 'export':
        export_obj(args)
    elif args.command == 'add':
        add_dep_obj(args)
    elif args.command == 'delete':
        delete_obj(args)
    else:
        trans_command(args, remaining)


def trans_command(args, remaining):
    git_command = ["git", args.command]
    if args.argument:
        git_command.append(args.argument)
    git_command.extend(remaining)
    try:
        # subprocess.run 默认使用系统编码，通常无需指定 encoding
        subprocess.run(git_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error while executing command: {e}")


def before_check(args):
    if args.command == "install": return True

    # 检查是否安装
    installed = False
    if os.name == 'nt':
        if write_to_path.sys_env_is_exist("GIS_ROOT"): installed = True
    else:
        # Linux下如果能找到命令或者软链接，认为已安装
        if os.path.exists("/usr/local/bin/gis"): installed = True
        # 或者开发环境下也允许运行 (非打包状态)
        if not getattr(sys, 'frozen', False): installed = True

    if not installed:
        # 如果是打包的二进制文件，必须先安装
        if os.name == 'nt':
            print("The program is not installed, please install it first: gis.exe install")
            return False
        elif getattr(sys, 'frozen', False):
            print("The program is not installed, please install it first: sudo ./gis install")
            return False

    # 检查配置
    lean_local_path = show_config("lean_local_path")
    # 如果配置缺失，尝试忽略，或者在install时生成
    if lean_local_path:
        sys_value = write_to_path.sys_env_is_exist("GIS_LEAN_ROOT")

        # 检查是否不一致 (简化逻辑，跨平台通用)
        is_path_modified = False
        if not sys_value:
            is_path_modified = True
        elif os.path.normpath(lean_local_path) != os.path.normpath(sys_value):
            is_path_modified = True

        if is_path_modified:
            print(f"{lean_local_path} was detected to be modified. Automatically modify system variables GIS_LEAN_ROOT")
            write_to_path.set_system_env("GIS_LEAN_ROOT", lean_local_path)

        if not os.path.exists(lean_local_path):
            try:
                os.makedirs(lean_local_path, exist_ok=True)
            except:
                pass
    return True


def install(args):
    # Windows 重复安装检查
    if os.name == 'nt' and write_to_path.sys_env_is_exist("GIS_ROOT"):
        print("Install Failed: The program has been installed before.")
        print("If reinstalling, please delete the system variables first:{GIS_ROOT}, {GIS_LEAN_ROOT}")
        return

    # Linux 简单提示
    if os.name != 'nt' and os.path.exists("/usr/local/bin/gis") and getattr(sys, 'frozen', False):
        print("Warning: /usr/local/bin/gis already exists. Overwriting...")

    if not write_to_path.is_admin():
        print("Install Failed: Administrator/Root privileges required.")
        return

    gis_install_path = str(MAIN_PATH)
    print("installing……")

    # 依赖检查与安装
    git_install = write_to_path.check_git_installed()
    cmake_install = write_to_path.check_cmake_installed()

    if not git_install or not cmake_install:
        print("Missing dependencies. Attempting auto-install...")
        write_to_path.execute_installation(not git_install, not cmake_install)

    check_gitconfig()

    # 再次检查依赖
    new_git_install = write_to_path.check_git_installed()
    new_cmake_install = write_to_path.check_cmake_installed()

    if new_git_install and new_cmake_install:
        # --- 自动生成配置 ---
        lean_local_path = show_config("lean_local_path")

        if lean_local_path is None:
            print("Config missing. Generating default config...")
            # 在当前安装目录生成
            gene_conf(gis_install_path)
            lean_local_path = show_config("lean_local_path")

            if lean_local_path is None:
                print(Fore.RED + "Fatal: Config generation failed." + Style.RESET_ALL)
                return

        # 创建目录
        if not os.path.exists(lean_local_path):
            try:
                os.makedirs(lean_local_path)
                print(f"Created directory: {lean_local_path}")
            except Exception as e:
                print(f"Error creating directory {lean_local_path}: {e}")
                print("Fatal: failed to create the lean directory")

        # 写入系统变量 (通用)
        # 移除平台判断，write_to_path 内部已处理
        write_to_path.set_system_env("GIS_LEAN_ROOT", lean_local_path)

        if os.name == 'nt':
            write_to_path.set_system_env("GIS_ROOT", gis_install_path)

        # 添加 Path / 创建软链接 (通用)
        write_to_path.add_system_path(gis_install_path)

        if args.lean: pass


def uninstall():
    if not write_to_path.is_admin():
        print("Uninstall Failed: Administrator/Root privileges required.")
        return

    print("uninstalling……")

    if os.name == 'nt':
        # Windows 卸载逻辑
        if not write_to_path.sys_env_is_exist("GIS_ROOT"):
            print("UnInstall Failed: Program not installed.")
            return
        GIS_INSTALL_PATH = write_to_path.delete_from_path(write_to_path.get_system_env_variable("GIS_ROOT"))
        GIS_LEAN_ROOT = write_to_path.delete_system_env_variable("GIS_LEAN_ROOT")
        GIS_ROOT = write_to_path.delete_system_env_variable("GIS_ROOT")
        if GIS_INSTALL_PATH and GIS_ROOT and GIS_LEAN_ROOT:
            print("Gis was successfully unloaded!")
        else:
            print("Gis unload failed!")
    else:
        # Linux 卸载逻辑
        write_to_path.delete_from_path(None)  # 移除软链接
        write_to_path.delete_system_env_variable("GIS_LEAN_ROOT")  # 移除 profile.d
        print("Gis symlinks and env vars removed.")

    flag = input("Whether to remove the lean environment package, Y/N？")
    if flag.lower() in ("y", "yes"):
        directory = show_config("lean_local_path")
        if directory and os.path.exists(directory) and os.path.isdir(directory):
            try:
                shutil.rmtree(directory)
                print(f"The lean environment package was deleted successfully!")
            except Exception as e:
                print(f"Failed to delete lean package: {e}")


def clone(args):
    if args.argument:
        if not args.dep and not args.lean:
            print(Fore.CYAN + "No flags provided. Defaulting to full clone (--dep --lean)..." + Style.RESET_ALL)
            args.dep = True
            args.lean = True
    work_path = os.getcwd()
    if args.argument:
        if args.dep:
            clone_repository(args.argument, os.getcwd())
            repo_name = os.path.basename(args.argument).replace('.git', '')
            repo_path = os.path.join(os.getcwd(), repo_name)
            update_dependencies(args, repo_path)
            if args.lean:
                os.chdir(work_path)
                os.chdir(repo_name)
                success = update_lean(args, os.path.join(os.getcwd()))
                if not success:
                    return
        else:
            clone_repository(args.argument, os.getcwd())
    else:
        if args.specific:
            install_dep(args, os.getcwd())


def update(args):
    if not args.dep and not args.lean:
        print(Fore.CYAN + "No flags provided. Defaulting to full update (--dep --lean)..." + Style.RESET_ALL)
        args.dep = True
        args.lean = True
    if args.dep:
        print(
            Fore.YELLOW + "WARNNING: This command will rewrite and DROP all your local changes on dependencies path." + Style.RESET_ALL)
        user_input = input("Do you want to continue? [Y/N]: ").strip().lower()
        if user_input not in ('y', 'yes'):
            print("Operation aborted by user.")
            return
        if args.specific:
            update_dependency_specific(args, os.getcwd(), args.specific)
        else:
            update_dependencies(args, os.getcwd())

    if args.lean:
        if args.specific:
            update_lean_specific(args)
        else:
            success = update_lean(args, os.path.join(os.getcwd()))
            if not success:
                return
            if not args.obj_name:
                print(Fore.YELLOW + "No specification for --obj-name. Exiting..." + Style.RESET_ALL)
                return
            if not args.no_obj:
                new_obj_name(args)
                gits.lean.import_dep_lean(args)
                gits.lean.check_obj(args)


def status(args):
    if args.dep:
        status_dep(os.getcwd())
    elif args.lean:
        if args.remote:
            status_lean_remote()
        else:
            status_lean_local(args, os.getcwd())
    if not args.dep and not args.lean:
        command = ['git', 'status']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, cwd=os.getcwd(), text=True)


def check_import(args):
    if args.import_check:
        check_commands(args)
    if args.object:
        check_obj()


def import_dep_lean(args):
    if not args.to_destination:
        print(Fore.YELLOW + f"The 'to' parameter was not provided." + Style.RESET_ALL)
        return
    gits.cmake.import_dep_lean(args)


def new_obj(args):
    gits.cmake.new_obj(args)


def export_obj(args):
    gits.cmake.export_obj(args)


def add_dep_obj(args):
    if args.dep:
        gits.cmake.add_dep(args.argument)
    elif args.obj_name:
        gits.cmake.add_obj(args)


def delete_obj(args):
    gits.cmake.delete_obj(args)


def version():
    ascii_art1 = text2art("GIS", font='standard')
    ascii_art2 = text2art(" POWERED BY SIA8-SOFT", font='standard')
    print(Fore.GREEN + ascii_art1 + Style.RESET_ALL)
    print(Fore.GREEN + ascii_art2 + Style.RESET_ALL)
    print(f"Local  Version:{config.VERSION}")
    print(f"OS            :{config.OS}")
    print(f"Publish Date  :{config.PUBLISH_DATE}")