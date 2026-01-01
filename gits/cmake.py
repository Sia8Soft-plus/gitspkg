import configparser
import os
import re
import subprocess
import textwrap

import paramiko
from colorama import Fore, Style
from pathlib import Path
import gits.lean
from gits import cmake_template, lean

# 定义系统默认编码
SYS_ENCODING = 'gbk' if os.name == 'nt' else 'utf-8'
def is_git_repository():
    """检查当前目录是否是一个Git仓库。"""
    try:
        # 运行一个安全的、只读的git命令来检查环境
        subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            check=True,
            capture_output=True  # 隐藏 'true' 的输出
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_commands(args):
    """
    这是一个调度函数，它处理 'check --import' 命令的所有逻辑，
    包括路径处理和递归，然后调用 gits.cmake.check_import。
    """
    if not args.argument:
        print(Fore.RED + "The 'check --import' command requires a path parameter." + Style.RESET_ALL)
        return

    target_path = args.argument
    absolute_path = os.path.abspath(target_path)

    if not os.path.exists(absolute_path):
        print(Fore.RED + f"The specified path does not exist: '{target_path}'" + Style.RESET_ALL)
        return

    # 根据递归标志，构建待检查的目录列表
    dirs_to_process = []

    if args.recursive:
        # --- 递归模式的逻辑 ---
        print(f"Recursive mode: Scanning '{target_path}' and all its subdirectories...")
        if not os.path.isdir(absolute_path):
            print(
                Fore.RED + f"Recursive check requires a directory, but '{target_path}' is not." + Style.RESET_ALL)
            return

        # os.walk 会遍历 absolute_path 目录本身，以及它下面的所有子目录。
        # 在每次循环中，`current_dir` 就是我们正在访问的目录。
        for current_dir, _, _ in os.walk(absolute_path):
            # 我们将访问到的每一个目录都加入待处理列表
            dirs_to_process.append(current_dir)

    else:
        # --- 非递归模式的逻辑 ---
        print(f"Single directory mode: Targeting '{target_path}'...")
        if not os.path.isdir(absolute_path):
            print(
                Fore.RED + f"The specified path '{target_path}' is not a valid directory." + Style.RESET_ALL)
            return

        # 只把用户输入的那一个目录加入待处理列表
        dirs_to_process.append(absolute_path)

    # 3. 循环调用 gits.cmake.check_import 进行实际检查
    found_any = False
    # sorted(list(set(...))) 组合可以去重并排序，保证输出整洁且一致
    # for dep_dir in sorted(list(set(dirs_to_process))):
    for dep_dir in dirs_to_process:

        if os.path.isfile(os.path.join(dep_dir, "cmake", "import.cmake")):
            found_any = True

            # 将绝对路径转换回相对路径，以保持 lean.py 函数的输出美观。
            relative_path_for_lean = os.path.relpath(dep_dir, os.getcwd())
            normalized_arg_path = relative_path_for_lean.replace('\\', '/')
            check_import(normalized_arg_path, True)

    if not found_any:
        print(
            Fore.YELLOW + "No valid dependency directories containing 'cmake/import.cmake' were found within the specified path." + Style.RESET_ALL)
    print("All checks completed.")


def check_import(path, import_check):
    if not import_check:
        print("The input command is incorrect.")

    print("-" * 40)
    print(f"Checking in: '{path}'")

    dependency_path = os.path.abspath(path)

    # 检查该依赖库相对路径是否存在，且必须是一个目录
    if not os.path.isdir(dependency_path):
        # 如果路径不存在或不是一个文件夹，则输出错误信息并返回 False
        print(Fore.RED + f"The dependency path does not exist or is not a valid directory." + Style.RESET_ALL)
        print("-" * 40)

    # 检查该依赖库的根目录下是否存在 cmake/import.cmake 文件
    cmake_file_path = os.path.join(dependency_path, "cmake", "import.cmake")

    if not os.path.isfile(cmake_file_path):
        # 如果 cmake/import.cmake 不存在或不是一个文件，则输出错误信息并返回 False
        print(Fore.RED + f"The 'cmake/import.cmake' file was not found in the '{path}' directory." + Style.RESET_ALL)

    try:
        with open(cmake_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 定义用于匹配 function(...)...endfunction() 块的正则表达式
        # re.DOTALL 使得 '.' 可以匹配包括换行在内的任意字符
        regex = re.compile(r"function\(([\w_]+)\s*.*?\)\s*.*?\bendfunction\b", re.DOTALL)

        # 找到所有匹配的函数块，并提取函数名 (捕获组 1)
        found_functions = regex.findall(content)
        # print(found_functions)
        # 如果没有找到任何函数，打印相应信息
        if not found_functions:
            print("Found CMake function: None")
            print("Support gits cmd:")

        # 打印找到的所有函数名
        print(f"Found CMake function: {', '.join(found_functions)}")

        # 初始化用于存储解析结果的变量
        import_function_valid = False
        add_targets = []

        # 获取依赖库的名称 (即其文件夹名)
        dependency_name = os.path.basename(dependency_path)

        # 遍历找到的函数名，进行分类和验证
        for func_name in found_functions:
            if func_name.startswith("import_"):
                # 这是一个 import 型函数
                extracted_dep_name = func_name[len("import_"):]
                if extracted_dep_name == dependency_name:
                    import_function_valid = True
                else:
                    # 依赖库名不匹配，输出警告
                    print(Fore.YELLOW +
                          f"The dependency name '{extracted_dep_name}' of the function '{func_name}' does not match the directory name '{dependency_name}'. "
                          f"Therefore, this function will be ignored." + Style.RESET_ALL)

            elif func_name.startswith("add_"):
                # 这是一个 add 型函数
                target_name = func_name[len("add_"):]
                add_targets.append(target_name)

        # 根据解析结果，格式化输出支持的 gits 命令
        print("Support gits cmd:")

        if import_function_valid:
            print(f"gits import {path} --to compile_obj")

        if add_targets:
            # 将所有目标名用空格连接
            targets_str = ' '.join(add_targets)
            print(f"gits add {path} --obj-name {targets_str}")

    except Exception as e:
        print(Fore.RED + f"  An error occurred while parsing the file: {e}" + Style.RESET_ALL)
    print("-" * 40)


def check_obj():
    cmakelist_path = os.path.abspath("CMakeLists.txt")
    # cmakelist_path = r"E:\GISTEST\CV_OPS\CMakeLists.txt"
    if not os.path.isfile(cmakelist_path):
        # 如果 cmakelist 不存在或不是一个文件，则输出错误信息并返回 False
        print(Fore.RED + f"The 'cmake/import.cmake' file was not found in the '{os.getcwd()}' directory.")
    try:
        with open(cmakelist_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(Fore.RED + f"Error: Failed to read the file '{cmakelist_path}'. Reason: {e}" + Style.RESET_ALL)
        return
    project_name_match = re.search(r"project\s*\(\s*(\w+)\s*\)", content, re.IGNORECASE)
    project_name = project_name_match.group(1) if project_name_match else "Unknown"

    add_subdir_regex = re.compile(r"(?m)^[ \t]*add_subdirectory\s*\(\s*([\w\/\.]+)\s+([\w\.]+)\s*\)", re.IGNORECASE)
    add_subdir_targets = add_subdir_regex.findall(content)

    add_custom_regex = re.compile(r"(?m)^[ \t]*add_(\w+)\s*\(", re.IGNORECASE)
    add_custom_targets = add_custom_regex.findall(content)
    EXCLUDED_KEYWORDS = ['subdirectory']

    # 过滤掉不希望出现的结果
    add_custom_targets = [
        name for name in add_custom_targets
        if name.lower() not in EXCLUDED_KEYWORDS
    ]

    print(f"Project: {project_name}")

    all_targets = []

    # 将 add_subdirectory 的结果添加到总列表
    for path, name in add_subdir_targets:
        # print(add_subdir_targets)
        all_targets.append(f"{name} (cmakefile at: {path})")

    # 将 add_XXX 的结果添加到总列表
    for name in add_custom_targets:
        # print(add_custom_targets)
        all_targets.append(name)

    if not all_targets:
        print("Found 0 compile objects.")
        return

    print(f"Found {len(all_targets)} compile objects:")
    for i, target_info in enumerate(all_targets, 1):
        print(f"{i}. {target_info}")


def check_CMakeLists(flag, cmake_dir, cmake_template_with_indent):
    cmake_list_file_path = os.path.join(cmake_dir, "CMakeLists.txt")
    if flag:
        if not os.path.exists(cmake_dir):
            print(f"The target directory '{cmake_dir}' does not exist. Creating...")
            os.makedirs(cmake_dir, exist_ok=True)
            print(f"The directory '{cmake_dir}' has been created.")
        elif not os.path.isdir(cmake_dir):
            print(f"The path '{cmake_dir}' already exists, but it is not a directory.")
            return
        if not os.path.exists(cmake_list_file_path):
            print(f"The file '{cmake_list_file_path}' does not exist. Creating and writing the template content...")
            cmake_template = textwrap.dedent(cmake_template_with_indent)

            try:
                with open(cmake_list_file_path, 'w', encoding='utf-8') as f:
                    f.write(cmake_template)
                print(f"'{cmake_list_file_path}' has been created.")
            except IOError as e:
                print(f"Failed to write to file '{cmake_list_file_path}': {e}")
        else:
            print("The CMakeLists.txt file already exists.")
    else:
        if not os.path.exists(cmake_dir):
            print(f"The target directory '{cmake_dir}' does not exist.")
            return
        elif not os.path.isdir(cmake_dir):
            print(f"The path '{cmake_dir}' already exists, but it is not a directory.")
            return
        if not os.path.exists(cmake_list_file_path):
            print("The CMakeLists.txt file does not exist.")
            return
        return True


def write_CMakeLists(target_cmake_file):
    # target_cmake_file = os.path.join(cmake_dir, "CMakeLists.txt")
    # --- 读取文件所有行到列表中 ---
    with open(target_cmake_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # --- 定位目标行 'set(SRC_LIST "")' ---
    target_line_content = 'set(SRC_LIST "")'
    target_index = -1

    for i, line in enumerate(lines):
        if line.strip() == target_line_content:
            target_index = i
            break  # 找到第一个就停止

    if target_index == -1:
        print(
            Fore.RED + f"The target line '{target_line_content}' was not found in the file '{target_cmake_file}'." + Style.RESET_ALL)
        return False
    print(f"The target '{target_line_content}' was found on the {target_index + 1}th line.")
    return lines, target_index


def import_dep_lean(args):
    project_root_abs = os.path.abspath(os.getcwd())
    target_dir_abs = os.path.abspath(args.to_destination)

    relative_path_to_root = os.path.relpath(project_root_abs, start=target_dir_abs)

    if relative_path_to_root == '.':
        cmake_root_path_prefix = ""
    else:
        cmake_root_path_prefix = relative_path_to_root.replace('\\', '/') + '/'
    validated_path = False  # 存储最终验证成功的路径
    is_path = '/' in args.argument or '\\' in args.argument
    if is_path:
        # --- 情况 1: 处理本地依赖库路径 ---
        full_path = os.path.abspath(args.argument)
        if os.path.isdir(full_path):
            validated_path = True  # 使用原始相对路径
            command = ['gis', 'check', f'{args.argument}', '--import']
            print(f"Running command: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, encoding=SYS_ENCODING, check=True)
            command_output = result.stdout
            # print(command_output)
            if f"gits import {args.argument}" in command_output:
                # # print("通过！准备写入")
                cmake_dir = os.path.abspath(args.to_destination)
                target_cmake_file = os.path.join(cmake_dir, "CMakeLists.txt")
                if not os.path.exists(target_cmake_file):
                    print(f"The target directory '{cmake_dir}' does not exist.")
                    print(f"The directory '{cmake_dir}' has been created.")
                    command = ['gis', 'new-obj', f'{args.to_destination}']
                    print(f"Running command: {' '.join(command)}")
                    result = subprocess.run(command, text=True, encoding=SYS_ENCODING, check=True)
                # else:
                #     project_name = os.path.basename(cmake_dir)
                #
                #     cmake_template_with_indent = f"""\
                #                     cmake_minimum_required(VERSION 3.0)
                #                     project({project_name})
                #                     message("GIS_LEAN_ROOT: " $ENV{{GIS_LEAN_ROOT}})
                #                     set(SRC_LIST "")
                #                     """
                #     check_CMakeLists(True, cmake_dir, cmake_template_with_indent)

                pattern = r"gits import\s+([\w\/\\.-]+)\s+--to"
                match = re.search(pattern, command_output, re.MULTILINE)

                if match:
                    dependency_path = match.group(1).strip()
                    dependency_name = os.path.basename(os.path.normpath(dependency_path))
                    dependency_path_cmake = dependency_path.replace('\\', '/')
                    # return dependency_name, dependency_path_cmake
                else:
                    print(
                        Fore.GREEN + "gis check ... --import The import parsing failed. No write information was obtained and it has been returned." + Style.RESET_ALL)
                    return

                try:
                    print(f"Parse to dependency name = '{dependency_name}', path = '{dependency_path}'")
                    target_cmake_file = os.path.join(cmake_dir, "CMakeLists.txt")
                    lines, target_index = write_CMakeLists(target_cmake_file)

                    # --- 生成要插入的新代码 ---
                    # 注意 ${...} 中的花括号需要加倍 {{...}} 来进行转义
                    code_to_insert = [
                        f"include({cmake_root_path_prefix}{dependency_path_cmake}/cmake/import.cmake)\n",
                        f"import_{dependency_name}({cmake_root_path_prefix}{dependency_path_cmake}/ {dependency_name}_src)\n",
                        f"list(APPEND SRC_LIST ${{{dependency_name}_src}})\n"
                    ]

                    # --- 检查是否已经插入过，避免重复 ---
                    # 我们只检查核心的 import 行是否存在
                    line_to_check = f"import_{dependency_name}({cmake_root_path_prefix}{dependency_path_cmake}/ {dependency_name}_src)"
                    if any(line_to_check in line for line in lines):
                        print(
                            Fore.YELLOW + "This dependency seems to already exist in the CMake file and does not need to be added again." + Style.RESET_ALL)
                        return True

                    # --- 在目标行后面插入新代码 ---
                    # 使用列表的切片赋值功能，在 target_index+1 的位置插入 code_to_insert 列表
                    lines[target_index + 1: target_index + 1] = code_to_insert

                    # --- 将修改后的所有行写回文件 ---
                    with open(target_cmake_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines)

                    print(
                        Fore.GREEN + f"The configuration dependent on '{dependency_name}' has been written to '{target_cmake_file}'." + Style.RESET_ALL)
                    return True

                except FileNotFoundError:
                    print(Fore.RED + f"The target file '{target_cmake_file}' does not exist." + Style.RESET_ALL)
                    return False
                except Exception as e:
                    print(Fore.RED + f"An exception occurred while processing the CMake file: {e}" + Style.RESET_ALL)
                    return False
            else:
                print("There are no import-type CMake functions in the import.camke file that depends on the library!")
                return
        else:
            # --- 情况 4 (分支a): 路径无效 ---
            print(Fore.RED + "The relative path of the dependent library does not exist." + Style.RESET_ALL)
            return
    else:
        # --- 处理 lean 包名 ---
        # print(f"信息: 识别到输入 '{args.argument}' 为一个 lean 包名。")
        package_local_path = os.path.join(gits.lean.lean_local_path, args.argument)

        # --- 情况 2: 检查本地 lean 包是否存在 ---
        if os.path.isdir(package_local_path):
            validated_path = True
        else:
            # 本地不存在，进入情况 3 和 4 的判断
            print(f"The 'lean' package '{args.argument}' is not available locally. Checking the remote server...")
            try:
                # 创建 SSH 客户端并连接
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # 自动接受未知主机密钥
                ssh.connect(gits.lean.lean_remote_ip, username=gits.lean.lean_remote_user,
                            password=gits.lean.lean_remote_pwd)
                # 创建 SFTP 会话

                with ssh.open_sftp() as sftp:
                    server_package = []
                    lean_remote_path = gits.lean.match_lean_remote()
                    server_packages = gits.lean.get_server_packages(sftp, lean_remote_path)
                    for key, value in server_packages.items():
                        package = key[:-4]
                        server_package.append(package)
                    # print(server_package)
                    found_server = False
                    if args.argument in server_package:
                        found_server = True
            except paramiko.AuthenticationException:
                print("Authentication failed. Please check the username and password.")
            except Exception as e:
                print(f" {e}")
            finally:
                ssh.close()  # 确保 SSH 连接关闭
            if found_server:
                print(f"The remote server has located the package '{args.argument}' and is ready for synchronization.")
                # 触发下载
                command = ['gis', 'update', '--lean', f'--specific={args.argument}']
                print(f"Running command: {' '.join(command)}")
                result = subprocess.run(command, text=True)
                if os.path.isdir(package_local_path):
                    validated_path = True
            else:
                # --- 情况 4 (分支b): 本地和远程都不存在 ---
                print(f"The 'lean' package '{args.argument}' could not be found on both the local and remote servers.")

        if validated_path:
            cmake_dir = os.path.abspath(args.to_destination)
            if not os.path.exists(cmake_dir):
                print(f"The target directory '{cmake_dir}' does not exist.")
                print(f"The directory '{cmake_dir}' has been created.")
                command = ['gis', 'new-obj', f'{args.to_destination}']
                print(f"Running command: {' '.join(command)}")
                result = subprocess.run(command, text=True, encoding=SYS_ENCODING, check=True)
            # else:
            #     project_name = os.path.basename(cmake_dir)
            #
            #     cmake_template_with_indent = f"""\
            #                     cmake_minimum_required(VERSION 3.0)
            #                     project({project_name})
            #                     message("GIS_LEAN_ROOT: " $ENV{{GIS_LEAN_ROOT}})
            #                     set(SRC_LIST "")
            #                     """
            #     check_CMakeLists(True, cmake_dir, cmake_template_with_indent)
            try:
                target_cmake_file = os.path.join(cmake_dir, "CMakeLists.txt")
                lines, target_index = write_CMakeLists(target_cmake_file)

                # --- 生成要插入的新代码 ---
                # 注意 ${...} 中的花括号需要加倍 {{...}} 来进行转义
                code_to_insert = [
                    f"import({args.argument})\n"
                ]

                # --- 检查是否已经插入过，避免重复 ---
                # 我们只检查核心的 import 行是否存在
                line_to_check = f"import({args.argument})"
                # print(line_to_check)
                if any(line_to_check in line for line in lines):
                    print(
                        Fore.YELLOW + f"This import({args.argument}) seems to already exist in the CMake file and does not need to be added again." + Style.RESET_ALL)
                    return True

                lines[target_index + 1: target_index + 1] = code_to_insert

                # --- 将修改后的所有行写回文件 ---
                with open(target_cmake_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

                print(
                    Fore.GREEN + f"The configuration dependent on import('{args.argument}') has been written to '{target_cmake_file}'." + Style.RESET_ALL)
                return True

            except FileNotFoundError:
                print(Fore.RED + f"The target file '{target_cmake_file}' does not exist." + Style.RESET_ALL)
                return False
            except Exception as e:
                print(Fore.RED + f"An exception occurred while processing the CMake file: {e}" + Style.RESET_ALL)
                return False
        else:
            print("Synchronous lean exception detected, program has exited!")
            return
    # print(validated_path)


def new_obj(args):
    root_dir_abs = Path.cwd()
    target_dir = root_dir_abs / args.argument
    project_name = target_dir.name
    if target_dir == Path.cwd().resolve():
        print("The target path is the root directory!")
        return
    relative_from_root = target_dir.relative_to(root_dir_abs)
    depth = len(relative_from_root.parts)
    if depth > 0:
        path_parts = ['..'] * depth + ['']
        root_dir_path_str = '/'.join(path_parts)
    else:
        root_dir_path_str = '.'
    target_command = ""
    if args.dll:
        target_command = "add_library(${PROJECT_NAME} SHARED ${SRC_LIST})"
        dep_work = f"deploy_{project_name}"
    elif args.lib:
        target_command = "add_library(${PROJECT_NAME} STATIC ${SRC_LIST})"
        dep_work = f"deploy_{project_name}"
    else:
        target_command = "add_executable(${PROJECT_NAME} ${SRC_LIST})"
        dep_work = "workspace"
    template = cmake_template.CMAKE_TEMPLATE
    cmake_template_with_indent = template.format(
        project_name=project_name,
        root_dir_path_str=root_dir_path_str,
        target_command=target_command,
        dep_work=dep_work
    )
    check_CMakeLists(True, args.argument, cmake_template_with_indent)
    print(Fore.YELLOW + "你自己写的文件还得自己编辑CMakeLists.txt" + Style.RESET_ALL)

    src_dir = root_dir_abs / "src"
    test_dir = root_dir_abs / "test"

    if not src_dir.is_dir():
        src_dir.mkdir()

    if not test_dir.is_dir():
        test_dir.mkdir()


def export_obj(args):
    val = check_CMakeLists(False, args.argument, None)
    if not val:
        return
    # print(args.argument)
    # print(args.obj_name)
    cmake_dir = os.path.join(os.getcwd(), "cmake")
    cmake_file_path = os.path.join(cmake_dir, "import.cmake")
    if not os.path.isfile(cmake_file_path):
        print(f"The 'cmake/import.cmake' file was not found in the '{os.getcwd()}' directory.")
        try:
            os.makedirs(cmake_dir, exist_ok=True)
            with open(cmake_file_path, 'w', encoding='utf-8') as f:
                pass
            print(f"Successfully created '{cmake_file_path}'.")
        except OSError as e:
            print(f"Failed to create file '{cmake_file_path}': {e}")

    project_root_name = os.path.basename(os.getcwd())

    function_name = f"add_{project_root_name}_{args.obj_name[0]}"

    target_dir_abs_path = os.path.abspath(args.argument)

    # 出发点 B 的绝对路径
    base_dir_abs_path = os.path.abspath(cmake_dir)

    # *** 使用 os.path.relpath 进行最终的正确计算 ***
    # 它会正确地生成 '..'
    try:
        relative_path_str = os.path.relpath(target_dir_abs_path, start=base_dir_abs_path)
    except Exception as e:
        # 捕获可能的错误
        print(f"计算相对路径时发生未知错误: {e}")
        return

    # 将 Windows 的反斜杠 \ 替换为 CMake 喜欢的正斜杠 /
    cmake_relative_path_str = relative_path_str.replace('\\', '/')

    # gis export cmake/my_ops --obj-name my_good_ops


    new_function_code = textwrap.dedent(f"""\
                set({project_root_name}_IMPORT_CMAKE_ROOT ${{CMAKE_CURRENT_LIST_DIR}})
                function({function_name})
                    add_subdirectory("${{{project_root_name}_IMPORT_CMAKE_ROOT}}/{cmake_relative_path_str}" {project_root_name}_{args.obj_name[0]})
                endfunction()
            """)

    try:
        with open(cmake_file_path, 'r', encoding='utf-8') as f:
            existing_content = f.read()
    except FileNotFoundError:
        print(f"The file '{cmake_file_path}' does not exist. Please make sure it has been created first.")
        return

    if function_name in existing_content:
        print(f"The function '{function_name}' already exists in '{cmake_file_path}', so no need to add it.")
        return

    try:
        with open(cmake_file_path, 'a', encoding='utf-8') as f:
            f.write("\n\n")
            f.write(new_function_code)
        print(f"The function has been successfully added.")
        return
    except IOError as e:
        print(f"Failed to write to file '{cmake_file_path}': {e}")
        return


def add_dep(dep_url):
    # 1. 检查 Git 环境
    if not is_git_repository():
        print("The current directory is not a git repository. The command 'git init' will be executed.")
        command_init = ['git', 'init']
        print(f" Running command: {' '.join(command_init)}")
        subprocess.run(command_init, text=True, encoding=SYS_ENCODING, check=True)

    # 2. 解析参数 (URL 和 版本信息)
    parts = dep_url.split('==')
    url = parts[0].strip()

    branch_commit = None
    if len(parts) > 1:
        branch_commit = parts[1]

    # 3. 提取依赖名
    filename_with_ext = os.path.basename(url)
    dep_name = os.path.splitext(filename_with_ext)[0]

    dep_path = f'dependency/{dep_name}'
    dep_dir = os.path.join(os.getcwd(), "dependency", dep_name)

    # 4. 判断是否需要执行 'git submodule add'
    # 逻辑修改：如果目录不存在，或者 .gitmodules 里没有，才 add。
    # 如果目录存在，我们只做 update 和 checkout。

    need_to_add = False

    if os.path.exists(dep_dir):
        if not os.path.isdir(dep_dir):
            print(f"Error: The path '{dep_dir}' exists but is not a directory.")
            return
        else:
            print(f"Directory '{dep_dir}' exists. Skipping 'submodule add', checking version...")
    else:
        # 目录不存在，说明是新的，需要 add
        need_to_add = True

    # 额外检查 .gitmodules 以防目录删了但配置还在
    if need_to_add:
        gitmodules_path = os.path.join(os.getcwd(), '.gitmodules')
        if os.path.isfile(gitmodules_path):
            config = configparser.ConfigParser()
            try:
                config.read(gitmodules_path, encoding='utf-8')
                section_name = f'submodule "{dep_path}"'
                if config.has_section(section_name):
                    print(f"Submodule '{dep_path}' defined in .gitmodules but folder missing. Will run update.")
                    need_to_add = False  # 配置还在，不需要 add，只需要 update
            except configparser.Error as e:
                print(f"Warning: Failed to parse .gitmodules. Error: {e}")
                return False

    # 5. 执行 Add (仅在需要时)
    if need_to_add:
        command_add = ['git', 'submodule', 'add', url, dep_path]
        print(f" Running command: {' '.join(command_add)}")
        try:
            result_add = subprocess.run(command_add, capture_output=True, text=True, encoding=SYS_ENCODING, check=True)
            print("Submodule added successfully.")
            print(result_add.stdout)
        except subprocess.CalledProcessError as e:
            print("Error adding submodule:")
            print(e.stderr)
            return

    # 6. 执行 Update (无论是否新建，都建议运行，确保子模块内容被拉取)
    # --init 确保初始化，--recursive 确保递归
    command_update = ['git', 'submodule', 'update', '--init', '--recursive', dep_path]
    print(f"Running command: {' '.join(command_update)}")
    try:
        subprocess.run(command_update, capture_output=True, text=True, encoding=SYS_ENCODING, check=True)
        print("Submodule updated.")
    except subprocess.CalledProcessError as e:
        print("Error during recursive update:")
        print(e.stderr)

    # 7. 解析具体的 Branch / Commit
    branch_name = None
    commit_name = None

    if branch_commit:
        clean_info = branch_commit.replace('[', '').replace(']', '').strip()
        if ":" in clean_info:
            parts1 = clean_info.split(':')
            branch_name = parts1[0].strip() if parts1[0].strip() else None
            if len(parts1) > 1:
                commit_name = parts1[1].strip()
        else:
            branch_name = clean_info
            commit_name = None

    # 8. 切换版本 (Checkout)

    if branch_name or commit_name:
        print(f"Configuring version for {dep_path}...")

        # 必须 fetch，防止新 Commit 还没拉下来
        subprocess.run(
            ['git', 'fetch', '--all'],
            cwd=dep_dir,
            capture_output=True, text=True, encoding=SYS_ENCODING
        )

        try:
            if commit_name:
                print(f"-> Switching to Commit: {commit_name}")
                subprocess.run(
                    ['git', 'checkout', commit_name],
                    cwd=dep_dir,
                    capture_output=True, text=True, encoding=SYS_ENCODING
                )
            elif branch_name:
                print(f"-> Switching to Branch: {branch_name}")
                subprocess.run(
                    ['git', 'checkout', branch_name],
                    cwd=dep_dir,
                    capture_output=True, text=True, encoding=SYS_ENCODING
                )
                # # 如果是切换分支，顺手拉取最新代码
                # subprocess.run(
                #     ['git', 'pull', 'origin', branch_name],
                #     cwd=dep_dir,
                #     capture_output=True, text=True, encoding=SYS_ENCODING, check=False
                # )
        except subprocess.CalledProcessError as e:
            print(f"Failed to switch version: {e.stderr}")


def add_obj(args):
    work_path = os.getcwd()
    # os.chdir(args.argument)
    command = ['gis', 'check', '.', '--import']
    print(f"Running command: {' '.join(command)} in {os.path.join(work_path, args.argument)}")
    try:
        result = subprocess.run(command, cwd=os.path.join(work_path, args.argument), capture_output=True, text=True,
                                encoding=SYS_ENCODING, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error executing 'gis' command: {e}")
        return

    command_output = result.stdout
    available_objects = set()
    prefix = "Found CMake function: "
    for line in command_output.splitlines():
        clean_line = line.strip()

        if clean_line.startswith(prefix):
            functions_str = clean_line[len(prefix):]

            function_names_list = functions_str.split(',')

            for name in function_names_list:
                name = name.strip()
                # 查找第一个下划线的位置
                first_underscore_index = name.find('_')
                # 如果找到了下划线，则提取其后的部分
                if first_underscore_index != -1:
                    extracted_name = name[first_underscore_index + 1:]
                    available_objects.add(extracted_name)

            break

    project_name = os.path.basename(work_path)
    # cmake_template_with_indent = f"""\
    #     cmake_minimum_required(VERSION 3.0)
    #     project({project_name})
    #     include($ENV{{GIS_LEAN_ROOT}}/import.cmake)
    #     """
    template_from_config = cmake_template.CMAKE_BASE_TEMPLATE

    formatted_template = template_from_config.format(project_name=project_name)
    content_to_append = textwrap.dedent(formatted_template)
    check_CMakeLists(True, work_path, content_to_append)

    cmakelists_path = os.path.join(work_path, "CMakeLists.txt")

    valid_objs_to_add = []
    for obj_name in args.obj_name:
        if obj_name in available_objects:
            valid_objs_to_add.append(obj_name)
        else:
            # 满足需求2: 如果目标不存在于依赖库中，则输出警告并跳过
            print(f"Warning: The object '{obj_name}' does not exist in the dependency '{args.argument}'. Skipping.")

    # 如果没有有效的目标可以添加，就提前结束
    if not valid_objs_to_add:
        print("No valid objects to add.")
        return

    try:
        with open(cmakelists_path, 'r', encoding='utf-8') as f:
            current_content = f.read()
    except IOError as e:
        print(f"Error: Failed to read {cmakelists_path}: {e}")
        return

    include_statement = f"include(${{CMAKE_SOURCE_DIR}}/{args.argument}/cmake/import.cmake)"

    add_statements = [f"add_{obj_name}()" for obj_name in valid_objs_to_add]

    # 将要追加的内容构建成一个列表
    content_to_write = []

    # 只有当 include 语句不在文件中时才添加它
    if include_statement not in current_content:
        content_to_write.append(include_statement)

    # content_to_write.extend(add_statements)
    for statement in add_statements:
        if statement not in current_content:
            content_to_write.append(statement)
        else:
            # (可选) 打印一个提示，告诉用户这个对象已经存在了
            print(f"Info: Target '{statement}' already exists in CMakeLists.txt. Skipping.")
    # 如果有内容需要写入
    if content_to_write:
        print(f"Adding targets to {cmakelists_path}...")
        try:
            with open(cmakelists_path, 'a', encoding='utf-8') as f:
                # 在开头加一个换行符，并在每个语句后加换行
                f.write('\n' + '\n'.join(content_to_write))
            print("Append successful.")
        except IOError as e:
            print(f"Error: Failed to append to {cmakelists_path}: {e}")


def delete_obj(args):
    work_path = os.getcwd()
    command = ['gis', 'check', '--obj']
    print(f"Running command: {' '.join(command)}")
    try:
        result = subprocess.run(command, cwd=work_path, capture_output=True, text=True,
                                encoding=SYS_ENCODING, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error checking objects: {e}")
        return
    command_output = result.stdout
    objects = []
    for line in command_output.splitlines():
        clean_line = line.strip()
        parts = clean_line.split()
        if len(parts) > 1 and parts[0][:-1].isdigit() and parts[0].endswith('.'):
            object_name = parts[1]
            objects.append(object_name)

    cmakelists_path = os.path.join(work_path, "CMakeLists.txt")
    if not os.path.exists(cmakelists_path):
        print(f"The path '{cmakelists_path}' does not exist.")
        return
    try:
        with open(cmakelists_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except IOError as e:
        print(f"Error reading file '{cmakelists_path}': {e}")
        return

    lines_to_process = lines[:]
    original_line_count = len(lines_to_process)

    for obj_name in args.obj_name:
        if obj_name not in objects:
            print(f"The {obj_name} does not exist.")
            continue  # 使用 continue 来跳过无效的对象

        target_add_line = f"add_{obj_name}()"

        temp_lines_after_delete = []
        i = 0
        lines_removed_for_this_obj = False

        while i < len(lines_to_process):
            current_line_stripped = lines_to_process[i].strip()

            if current_line_stripped == target_add_line:
                if temp_lines_after_delete:
                    previous_line_stripped = temp_lines_after_delete[-1].strip()

                    if previous_line_stripped.startswith('include('):
                        print(f"Found and removing pair for '{obj_name}':")
                        print(f"  -> {previous_line_stripped}")
                        print(f"  -> {current_line_stripped}")

                        temp_lines_after_delete.pop()
                        lines_removed_for_this_obj = True
                    else:

                        print(f"Found and removing standalone 'add' line for '{obj_name}'.")
                        lines_removed_for_this_obj = True
                else:
                    print(f"Found and removing 'add' line at file start for '{obj_name}'.")
                    lines_removed_for_this_obj = True

                i += 1
                continue

            temp_lines_after_delete.append(lines_to_process[i])
            i += 1

        lines_to_process = temp_lines_after_delete

        if not lines_removed_for_this_obj:
            print(f"Did not find any lines to remove for object '{obj_name}'.")

    if len(lines_to_process) < original_line_count:
        print(f"Writing updated content back to '{cmakelists_path}'...")
        try:
            with open(cmakelists_path, 'w', encoding='utf-8') as f:
                f.writelines(lines_to_process)
            print("File updated successfully.")
        except IOError as e:
            print(f"Error writing to file '{cmakelists_path}': {e}")
    else:
        print("No changes were made to the CMakeLists.txt file.")
