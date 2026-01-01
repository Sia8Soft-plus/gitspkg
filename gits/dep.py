import re
import subprocess
import os
from colorama import Fore, Style, init

from gits import cmake
from gits.config import show_config

init()
# def update_submodules_based_on_url(start_path, url_prefix):
#     """
#     解析.gitmodules文件，更新符合特定 URL 前缀的子模块。
#     递归执行git submodule update --remote --init命令
#     """
#     gitmodules_path = os.path.join(start_path, '.gitmodules')
#
#     # 检查当前目录中是否有 .gitmodules 文件
#     if os.path.exists(gitmodules_path):
#         print(f"Processing .gitmodules in {start_path}")
#
#         # 解析 .gitmodules 文件
#         with open(gitmodules_path, 'r') as file:
#             modules_content = file.read()
#
#         modules = modules_content.split('[submodule')
#         all_urls_match = True
#         submodule_paths = []
#
#         # 检查所有子模块的 URL 是否符合前缀要求
#         for module in modules[1:]:  # 跳过第一个分割结果
#             path = None
#             url = None
#             for line in module.strip().split('\n'):
#                 if line.strip().startswith('path ='):
#                     path = line.strip().split('=')[1].strip()
#                 elif line.strip().startswith('url ='):
#                     url = line.strip().split('=')[1].strip()
#
#             if url and url.startswith(url_prefix):
#                 submodule_paths.append(path)
#             else:
#                 all_urls_match = False
#
#         # 如果所有 URL 都匹配前缀，执行更新
#         if all_urls_match and submodule_paths:
#             try:
#
#                 subprocess.run(['git', 'submodule', 'update', '--remote', '--init'], cwd=start_path, check=True)
#                 # 递归更新每个符合条件的子模块
#                 for path in submodule_paths:
#                     full_path = os.path.join(start_path, path)
#                     update_submodules_based_on_url(full_path, url_prefix)
#             except subprocess.CalledProcessError as e:
#                 print(f"Failed to update submodules in {start_path}: {e}")
#
#
#     else:
#         # 如果没有 .gitmodules 文件，执行更新但不再递归
#         try:
#             subprocess.run(['git', 'submodule', 'update', '--remote', '--init'], cwd=start_path, check=True)
#         except subprocess.CalledProcessError as e:
#             print(f"Failed to update submodule at {start_path}: {e}")

def update_submodules_based_on_url(start_path, url_prefix):
    """
    解析.gitmodules文件，更新符合特定 URL 前缀的子模块。
    递归执行git submodule update --remote --init命令
    """
    gitmodules_path = os.path.join(start_path, '.gitmodules')

    # 核心逻辑：只在当前目录确实包含 .gitmodules 文件时，才进行处理
    if os.path.exists(gitmodules_path):
        print(f"Processing .gitmodules in {start_path}")

        # 解析 .gitmodules 文件
        with open(gitmodules_path, 'r') as file:
            modules_content = file.read()

        modules = modules_content.split('[submodule')
        all_urls_match = True
        submodule_paths = []

        # 检查所有子模块的 URL 是否符合前缀要求
        for module in modules[1:]:  # 跳过第一个分割结果
            path = None
            url = None
            for line in module.strip().split('\n'):
                if line.strip().startswith('path ='):
                    path = line.strip().split('=')[1].strip()
                elif line.strip().startswith('url ='):
                    url = line.strip().split('=')[1].strip()

            if url and url.startswith(url_prefix):
                submodule_paths.append(path)
            else:
                all_urls_match = False

        # 如果所有 URL 都匹配前缀，执行更新
        if all_urls_match and submodule_paths:
            try:
                # 首先，更新当前层级的所有子模块。
                # 这会将子模块的代码克隆下来，创建对应的目录。
                # 【修改点 1】我们只更新符合条件的子模块，而不是全部
                command_to_run = ['git', 'submodule', 'update', '--init'] + submodule_paths
                print(f"Updating submodules in {start_path}: {' '.join(command_to_run)}")
                subprocess.run(command_to_run, cwd=start_path, check=True)

                # 然后，对刚刚更新下来的每一个子模块目录，进行递归调用
                for path in submodule_paths:
                    full_path = os.path.join(start_path, path)

                    # 【修改点 2，最关键的修复】
                    # 在递归之前，必须检查拼接出的路径是否是一个真实存在的目录
                    if os.path.isdir(full_path):
                        update_submodules_based_on_url(full_path, url_prefix)
                    else:
                        # 这种情况通常发生在子模块更新失败或 .gitmodules 配置错误
                        print(
                            f"{Fore.YELLOW}Warning: Submodule path is not a directory, skipping recursion for: {full_path}{Style.RESET_ALL}")

            except subprocess.CalledProcessError as e:
                print(f"{Fore.RED}Failed to update submodules in {start_path}: {e}{Style.RESET_ALL}")




def get_all_submodule_paths(base_directory):
    """
    获取所有子模块的完整路径，包括嵌套的子模块。
    """

    def parse_gitmodules(file_path):
        """解析 .gitmodules 文件，获取子模块路径"""
        submodule_paths = []
        current_submodule = None
        base_url = show_config("base_url")
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line.startswith('[submodule'):
                        # 开始新的子模块
                        if current_submodule:
                            # 只添加符合条件的子模块
                            if current_submodule.get('url', '').startswith(base_url):
                                submodule_paths.append(current_submodule)
                        current_submodule = {}
                    elif '=' in line and current_submodule is not None:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        current_submodule[key] = value

                # 添加最后一个子模块
                if current_submodule and current_submodule.get('url', '').startswith(base_url):
                    submodule_paths.append(current_submodule)

        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")

        return submodule_paths

    def extract_paths(submodules):
        """提取路径"""
        paths = []
        for submodule in submodules:
            path = submodule.get('path', None)
            if path:
                paths.append(path)
        return paths

    def recursive_submodule_paths(base_path, parent_path=""):
        """递归获取所有子模块路径"""
        all_paths = []
        gitmodules_path = os.path.join(base_path, '.gitmodules')

        if os.path.exists(gitmodules_path):
            submodules = parse_gitmodules(gitmodules_path)
            paths = extract_paths(submodules)

            for path in paths:
                full_path = os.path.join(parent_path, path) if parent_path else path
                all_paths.append(full_path)  # 添加完整路径
                # 递归查找嵌套子模块
                nested_paths = recursive_submodule_paths(os.path.join(base_path, path), full_path)
                all_paths.extend(nested_paths)

        return all_paths

    # 从指定的基目录开始递归查找子模块路径
    return recursive_submodule_paths(base_directory)


def generate_dependency_tree(deps):
    """
    打印依赖树。
    """

    def clean_path(path):
        # 1. 首先统一将反斜杠替换为正斜杠，方便处理
        path = path.replace('\\', '/')
        # 2. 移除第一个 'dependency' 之前的内容 (支持 /dependency)
        path = re.sub(r'^.*?/dependency', '', path, 1)
        # 3. 处理中间的冗余路径层级
        path = re.sub(r'/(dependency|dependencies|third_party|denpendency)/', '/', path)
        # 4. 去除首尾斜杠
        return path.strip('/')

    def build_dependency_tree():
        tree = {}
        for path, status in deps.items():
            parts = clean_path(path).split('\\')
            node = tree
            for part in parts:
                if part not in node:
                    node[part] = {}
                node = node[part]
            node['_status'] = status
        return tree

    def print_tree(node, depth=0):
        indent = '    ' * depth
        for key, value in node.items():
            if key == '_status':
                continue
            status = value.get('_status', 0)
            if status == 0:
                color = Fore.GREEN
                additional_text = ""
            elif status == -1:
                color = Fore.RED
                additional_text = ""
            else:
                color = Fore.YELLOW
                additional_text = f" behind {status} commits"
            print(f"{indent}- {color}{key}{additional_text}{Style.RESET_ALL}")
            if isinstance(value, dict):
                print_tree(value, depth + 1)

    tree = build_dependency_tree()
    print_tree(tree)


def clone_repository(url, cwd=None):
    """
    通过 Git 克隆指定的仓库，并将所有输出直接显示到终端（与原生命令一致）。
    递归执行git clone [url]命令
    """

    command = ['git', 'clone', url]
    print(f"Running command: {' '.join(command)}")

    # 使用 subprocess.run 执行命令，输出会直接显示在终端
    result = subprocess.run(command, cwd=cwd, text=True)

    # 判断克隆是否成功
    if result.returncode == 0:
        print("Clone completed successfully.\n")
        print("-" * 35)
        return True
    else:
        print(f"Clone failed with exit code: {result.returncode}")
        print("-" * 35)


def get_mainfest_dep(args, pwd):
    dep_urls = []
    git_url_pattern = re.compile(r"^https?://[\w.-]+(:\d+)?/.+\.git")
    if args.dep:
        for root, dirs, files in os.walk(pwd):
            for file in files:
                should_process = False
                if args.manifest_filename:
                    if file == args.manifest_filename:
                        should_process = True
                else:
                    if file.endswith('.manifest'):
                        should_process = True
                if not should_process:
                    continue
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            clean_line = line.strip()
                            clean_line_no_comment = clean_line.split('#')[0].strip()
                            if git_url_pattern.match(clean_line_no_comment):
                                dep_urls.append(clean_line_no_comment)

                except UnicodeDecodeError:
                    print(f"Read failure: Encoding format error in {file} (非 UTF-8)")
                except Exception as e:
                    print(f"Read failure in {file}: {e}")
    for dep in dep_urls:
        cmake.add_dep(dep)


def update_dependencies(args, repo_path):
    """
    递归的克隆/更新所有子模块的依赖。
    执行git remote show origin、git checkout、git status、git restore、git pull命令
    """
    checking_deps = {}
    # 第一步：切换到项目根目录
    print(f"Changing directory to {repo_path}")
    print(repo_path)
    os.chdir(repo_path)
    base_url = show_config("base_url")
    # 第二步：拉取所有依赖代码

    update_submodules_based_on_url(repo_path, base_url)

    print("-" * 35)
    # 第三步：遍历 .gitmodules 文件，获取所有依赖库路径
    base_directory = os.getcwd()  # 获取当前工作目录
    all_submodule_paths = get_all_submodule_paths(base_directory)

    # print("All submodule paths (including nested):")
    # for path in sorted(set(all_submodule_paths)):  # 排序并去重
    #     print(path)
    print(f"Checking all dependenies of {repo_path}...")
    normalized_paths = [os.path.join(*path.replace('\\', '/').split('/')) for path in all_submodule_paths]
    for path in normalized_paths:
        print("-" * 35)
        os.chdir(os.path.join(repo_path, path))
        print(f"The current path is：{os.getcwd()}")

        # 执行命令并捕获输出
        command = ['git', 'remote', 'show', 'origin']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # print(result.stdout + result.stderr)
        # print("-" * 35)
        # 确保命令成功执行
        if result.returncode != 0:
            print("Error executing git command:", result.stderr)
            return None
        # 解析输出
        branch_name = None
        for line in result.stdout.splitlines():
            if 'HEAD branch' in line:
                # 分割字符串并获取分支名
                branch_name = line.split(':')[-1].strip()

        command = ['git', 'checkout', branch_name]
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # print("-" * 35)

        command = ['git', 'status']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # 确保命令成功执行
        if result.returncode != 0:
            print("Error executing git command:", result.stderr)
            # return None

        # 解析输出
        print(result.stdout)
        print(result.stderr)
        # print("-" * 35)
        status_result_out = result.stderr + result.stdout
        for line in status_result_out.splitlines():
            if "Untracked files" in line or "Changes not staged for commit" in line or "Changes to be committed" in line:
                print(
                    Fore.YELLOW + "There may be untracked files, changes that have been modified but not staged, changes that have been staged, and git restore!" + Style.RESET_ALL)
                # print("-" * 35)
                command = ['git', 'restore', '--staged', '--worktree', os.getcwd()]
                print(f"Running command: {' '.join(command)}")
                result = subprocess.run(command, text=True)
                # print("-" * 35)
                break
            elif "nothing to commit, working tree clean" in line:
                # 分割字符串并获取分支名
                print(
                    Fore.GREEN + "The local main branch is synchronized with the main branch in the remote repo. There are no local unpushed commits, and no new commits unpulled remotely." + Style.RESET_ALL)
                break
        command = ['git', 'pull', 'origin', branch_name]
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        pull_result_out = result.stderr + result.stdout
        print(pull_result_out)
        # print("-" * 35)
        for line in pull_result_out.splitlines():
            if "Already up to date" in line:
                checking_deps[os.getcwd()] = 0
                break
            elif "Updating" in line or "Fast-forward" in line:
                checking_deps[os.getcwd()] = 0
                break
            elif "Auto-merging" in line:
                checking_deps[os.getcwd()] = -1
                break
    print("-" * 35)
    for key, value in checking_deps.items():
        if value == 0:
            print(f"Checking dep {key}...")
            print(Fore.GREEN + "PASS" + Style.RESET_ALL)
        else:
            print(f"Checking dep {key}...")
            print(Fore.RED + "NO PASS" + Style.RESET_ALL)
    print("-" * 35)
    # 生成依赖树
    print("Dependencies fetch and check process finish~")
    print("Dependency Tree:")
    last_part = os.path.basename(repo_path)
    print(last_part)
    generate_dependency_tree(checking_deps)
    print("-" * 35)

    get_mainfest_dep(args, base_directory)


def update_dependency_specific(args, cwd, specific_dep):
    """
        更新特定子模块的依赖。
        执行git remote show origin、git checkout、git status、git restore、git pull命令
    """

    checking_deps = {}

    path_dep = os.path.join(os.getcwd(), specific_dep)

    os.chdir(path_dep)

    base_url = show_config("base_url")
    update_submodules_based_on_url(path_dep, base_url)
    print("-" * 35)

    base_directory = os.getcwd()  # 获取当前工作目录
    all_submodule_paths = get_all_submodule_paths(base_directory)

    print(f"Checking dependenies of {specific_dep}...")
    normalized_paths = [os.path.join(*path.replace('\\', '/').split('/')) for path in all_submodule_paths]
    for path in normalized_paths:
        print("-" * 35)
        os.chdir(os.path.join(cwd, specific_dep, path))
        print(f"当前路径为：{os.getcwd()}")

        # 执行命令并捕获输出
        command = ['git', 'remote', 'show', 'origin']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # print(result.stdout + result.stderr)
        # print("-" * 35)
        # 确保命令成功执行
        if result.returncode != 0:
            print("Error executing git command:", result.stderr)
            return None
        # 解析输出
        branch_name = None
        for line in result.stdout.splitlines():
            if 'HEAD branch' in line:
                # 分割字符串并获取分支名
                branch_name = line.split(':')[-1].strip()

        command = ['git', 'checkout', branch_name]
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # print("-" * 35)

        command = ['git', 'status']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # 确保命令成功执行
        if result.returncode != 0:
            print("Error executing git command:", result.stderr)
            # return None

        # 解析输出
        print(result.stdout)
        print(result.stderr)
        # print("-" * 35)
        status_result_out = result.stderr + result.stdout
        for line in status_result_out.splitlines():
            if "Untracked files" in line or "Changes not staged for commit" in line or "Changes to be committed" in line:
                print(
                    Fore.YELLOW + "There may be untracked files, changes that have been modified but not staged, changes that have been staged, and git restore!" + Style.RESET_ALL)
                # print("-" * 35)
                command = ['git', 'restore', '--staged', '--worktree', os.getcwd()]
                print(f"Running command: {' '.join(command)}")
                result = subprocess.run(command, text=True)
                # print("-" * 35)
                break
            elif "nothing to commit, working tree clean" in line:
                # 分割字符串并获取分支名
                print(
                    Fore.GREEN + "The local main branch is synchronized with the main branch in the remote repo. There are no local unpushed commits, and no new commits unpulled remotely." + Style.RESET_ALL)
                break
        command = ['git', 'pull', 'origin', branch_name]
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        pull_result_out = result.stderr + result.stdout
        print(pull_result_out)
        # print("-" * 35)
        for line in pull_result_out.splitlines():
            if "Already up to date" in line:
                checking_deps[os.getcwd()] = 0
                break
            elif "Updating" in line or "Fast-forward" in line:
                checking_deps[os.getcwd()] = 0
                break
            elif "Auto-merging" in line:
                checking_deps[os.getcwd()] = -1
                break
    print("-" * 35)
    for key, value in checking_deps.items():
        if value == 0:
            print(f"Checking dep {key}...")
            print(Fore.GREEN + "PASS" + Style.RESET_ALL)
        else:
            print(f"Checking dep {key}...")
            print(Fore.RED + "NO PASS" + Style.RESET_ALL)
    print("-" * 35)
    # 生成依赖树
    print("Dependencies fetch and check process finish~")
    print("Dependency Tree:")
    last_part = os.path.basename(specific_dep)
    print(last_part)
    generate_dependency_tree(checking_deps)
    print("-" * 35)

    get_mainfest_dep(args, base_directory)


def status_dep(repo_path):
    """
       查看项目所有依赖的状态。
       执行git remote show origin、git checkout、git status命令
    """

    checking_deps = {}
    all_submodule_paths = get_all_submodule_paths(repo_path)
    normalized_paths = [os.path.join(*path.replace('\\', '/').split('/')) for path in all_submodule_paths]
    for path in normalized_paths:
        print("-" * 35)
        os.chdir(os.path.join(repo_path, path))
        print(f"The current path is：{os.getcwd()}")
        command = ['git', 'fetch']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, text=True)

        # # 执行命令并捕获输出
        # command = ['git', 'remote', 'show', 'origin']
        # print(f"Running command: {' '.join(command)}")
        # result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # # print(result.stdout + result.stderr)
        #
        # if result.returncode != 0:
        #     print("Error executing git command:", result.stderr)
        #
        # # 解析输出
        # branch_name = None
        # for line in result.stdout.splitlines():
        #     if 'HEAD branch' in line:
        #         # 分割字符串并获取分支名
        #         branch_name = line.split(':')[-1].strip()
        #
        # command = ['git', 'checkout', branch_name]
        # print(f"Running command: {' '.join(command)}")
        # result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # # print("-" * 35)

        command = ['git', 'status']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # 确保命令成功执行
        if result.returncode != 0:
            print("Error executing git command:", result.stderr)
            # return None

        # 解析输出
        print(result.stdout)
        print(result.stderr)
        status_result_out = result.stderr + result.stdout

        for line in status_result_out.splitlines():
            if "Your branch is up to date with " in line or "Your branch is ahead of " in line:
                checking_deps[os.getcwd()] = 0
                break
            elif "Your branch is behind" in line:
                # match = re.search(r"behind 'origin/(master|main)' by (\d+) commit[s]?", line)
                match = re.search(r"behind\s+'origin/([^']+)'\s+by\s+(\d+)\s+commit[s]?", line, re.IGNORECASE)
                if match:
                    num_commits = int(match.group(2))  # group(2) 是 (\d+)
                    print(f"The number of behind commits is{num_commits}")
                    checking_deps[os.getcwd()] = num_commits
            elif "HEAD detached" in line:
                # 提取 Commit ID 显示出来
                match = re.search(r"HEAD detached at (\S+)", line)
                commit_id = match.group(1) if match else "unknown"
                print(f"Status: Locked at {commit_id} (Detached HEAD)")
                checking_deps[os.getcwd()] = 0  # 视为正常状态 (0)
                break
    generate_dependency_tree(checking_deps)


def install_dep(args, cwd):
    """
       下载特定子模块的依赖。
       执行git remote show origin、git checkout、git status、git restore、git pull命令
    """
    path = args.specific
    checking_deps = {}
    path1 = os.path.join(cwd, path)

    base_url = show_config("base_url")
    update_submodules_based_on_url(path1, base_url)

    repo_path = os.path.join(cwd, path)

    all_submodule_paths = get_all_submodule_paths(repo_path)

    # print("All submodule paths (including nested):")
    # for path in sorted(set(all_submodule_paths)):  # 排序并去重
    #     print(path)

    print(f"Checking  dependency of {repo_path}...")
    normalized_paths = [os.path.join(*path.replace('\\', '/').split('/')) for path in all_submodule_paths]
    for path in normalized_paths:
        print("-" * 35)
        os.chdir(os.path.join(repo_path, path))
        print(f"The current path is {os.getcwd()}")

        # 执行命令并捕获输出
        command = ['git', 'remote', 'show', 'origin']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # print(result.stdout + result.stderr)
        # print("-" * 35)
        # 确保命令成功执行
        if result.returncode != 0:
            print("Error executing git command:", result.stderr)
            return None
        # 解析输出
        branch_name = None
        for line in result.stdout.splitlines():
            if 'HEAD branch' in line:
                # 分割字符串并获取分支名
                branch_name = line.split(':')[-1].strip()

        command = ['git', 'checkout', branch_name]
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # print("-" * 35)

        command = ['git', 'status']
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # 确保命令成功执行
        if result.returncode != 0:
            print("Error executing git command:", result.stderr)
            # return None

        # 解析输出
        print(result.stdout)
        print(result.stderr)
        # print("-" * 35)
        status_result_out = result.stderr + result.stdout
        for line in status_result_out.splitlines():
            if "Untracked files" in line or "Changes not staged for commit" in line or "Changes to be committed" in line:
                print(
                    Fore.YELLOW + "There may be untracked files, changes that have been modified but not staged, changes that have been staged, and git restore!" + Style.RESET_ALL)
                # print("-" * 35)
                command = ['git', 'restore', '--staged', '--worktree', os.getcwd()]
                print(f"Running command: {' '.join(command)}")
                result = subprocess.run(command, text=True)
                # print("-" * 35)
                break
            elif "nothing to commit, working tree clean" in line:
                # 分割字符串并获取分支名
                print(
                    Fore.GREEN + "The local main branch is synchronized with the main branch in the remote repo. There are no local unpushed commits, and no new commits unpulled remotely." + Style.RESET_ALL)
                break
        command = ['git', 'pull', 'origin', branch_name]
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        pull_result_out = result.stderr + result.stdout
        print(pull_result_out)
        # print("-" * 35)
        for line in pull_result_out.splitlines():
            if "Already up to date" in line:
                checking_deps[os.getcwd()] = 0
                break
            elif "Updating" in line or "Fast-forward" in line:
                checking_deps[os.getcwd()] = 0
                break
            elif "Auto-merging" in line:
                checking_deps[os.getcwd()] = -1
                break
    print("-" * 35)
    for key, value in checking_deps.items():
        if value == 0:
            print(f"Checking dep {key}...")
            print(Fore.GREEN + "PASS" + Style.RESET_ALL)
        else:
            print(f"Checking dep {key}...")
            print(Fore.RED + "NO PASS" + Style.RESET_ALL)
    print("-" * 35)
    # 生成依赖树
    print("Dependencies fetch and check process finish~")
    print("Dependency Tree:")
    last_part = os.path.basename(repo_path)
    print(last_part)
    generate_dependency_tree(checking_deps)
    print("-" * 35)

    get_mainfest_dep(args, cwd)
