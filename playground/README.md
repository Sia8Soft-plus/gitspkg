# GITS C++ Playground

在 Codespaces 终端中体验：**C++ 项目缺依赖，首次编译失败；执行 `gis update` 后编译、运行成功。**

[打开 GITS Codespaces](https://codespaces.new/Sia8Soft-plus/gitspkg)。点击 Create codespace，等待初始化完成，再选择 Terminal → New Terminal。终端默认位于 `.playground/project`。C++ 编译器由容器镜像提供，CMake 和 gits 依赖在初始化时自动准备。

## 1. 先尝试编译

逐条执行：

```bash
cmake -S . -B build
cmake --build build
```

CMake 配置应成功，编译应报 `demo_math.hpp: No such file or directory`。这是预期结果：`main.cpp` 引用了尚未下载的 `demo-math` 头文件。

## 2. 用 gits 补齐依赖

```bash
gis status --lean -m setup.manifest
gis update --lean -m setup.manifest --no-obj
```

首次 status 应显示 `1 missing packages`；update 应显示 `Succeed packages num: 1`，并把头文件复制到 `workspace/include/`。

清单只有两行：

```text
[GCC]
demo-math==1.0: copy include/* to ./workspace/include/
```

## 3. 再次编译并运行

```bash
cmake --build build
./build/delivery_smoke
```

预期输出：

```text
2 + 3 = 5
```

验证包内容、复制结果、状态、编译和运行：

```bash
python "$GITS_PLAYGROUND_ROOT/playground/verify.py" --build
```

应看到 `0 missing packages`、`copy ... OK!` 和 `PASS: built and ran C++ example: 2 + 3 = 5`。

再次执行 update 应显示 `Total lean packages num: 0`，表示复用缓存。

## 修改这个示例

| 文件 | 用途 |
| --- | --- |
| `playground/fixtures/main.cpp` | 示例工程，引用依赖并调用 `demo_math::add` |
| `playground/fixtures/CMakeLists.txt` | 构建配置，只从 `workspace/include` 查找业务头文件 |
| `playground/fixtures/setup.manifest` | 包版本与交付复制规则 |
| `playground/packages/demo-math/include/demo_math.hpp` | 依赖包的源文件，不会提前复制到工程 |
| `playground/bootstrap.py` | 生成演示包、独立配置、gis 启动器和示例工程 |

修改源文件后重新运行 `playground/bootstrap.py`。它会刷新示例工程和发生变化的演示压缩包，保留下载缓存；然后执行 update 重新交付。需要保留的工程修改应写回 `playground/fixtures`。正式发布包应递增版本并同步清单。

## 自动验收完整流程

```bash
python "$GITS_PLAYGROUND_ROOT/playground/test_demo.py"
```

该检查使用独立的临时工作区，验证：首次确实缺头文件并编译失败、真实 CLI 下载解压并复制、再次编译运行输出 5、重复初始化和更新复用缓存。它不重置当前项目和缓存。

## 更新已有 Codespace

在当前终端执行 `git pull --ff-only`，再按 Ctrl + Shift + P，选择 Codespaces: Rebuild Container。完成后新建终端，按上面的步骤操作。旧版文本测试包可以保留，新示例只需要 `demo-math`。

如果已经下载过 demo-math，首次构建会直接成功。自动验收命令始终在全新工作区验证缺依赖流程；手动从首次下载开始体验可新建 Codespace。

## Windows 本地运行

需要 Python 3.10 或更高版本及可用的 C++ 编译工具链。在仓库根目录的 PowerShell 中执行：

```powershell
python -m venv .playground/venv
& .playground/venv/Scripts/python.exe -m pip install -r playground/requirements.txt
& .playground/venv/Scripts/python.exe playground/bootstrap.py
& .playground/venv/Scripts/python.exe playground/run.py update --lean -m setup.manifest --no-obj
& .playground/venv/Scripts/python.exe playground/verify.py --build
```

如果使用 MinGW，可先设置 `$env:CMAKE_GENERATOR = 'MinGW Makefiles'`。也可以直接运行 `playground/test_demo.py` 验证完整流程。

## 实现范围

这里运行真实的 gits 源码、清单解析、版本匹配、下载处理、解压拍平、复制和状态检查；SSH/SFTP 由本地文件适配器代替。演示使用固定的 `linux-12` / `GCC` 包匹配标签，CMake 实际调用所在环境的编译器。包只有跨平台 C++ 头文件，无需生产服务器账号。

所有生成内容保存在 `.playground/`，不运行系统级 `gis install`。此示例验证源码依赖交付，不执行模型推理。Codespaces 使用 GitHub 账号的云端额度，测试结束可在 [Codespaces 列表](https://github.com/codespaces)中停止环境。
