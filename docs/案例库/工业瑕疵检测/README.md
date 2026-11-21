# 工业瑕疵检测

状态：待业务模型和设备验收。本文提供可复制的环境清单和单图检测操作，不代表产线系统已经完整实现。

## 1. 目标与前置条件

输入产品图片，输出缺陷类别、检测框和标注图，供质量判定模块使用。使用 [YOLO C++ 单图工程](../../../examples/yolo-edge/README.md)，模型要求与 [快速入门](../../01-快速入门.md) 一致。

需要 VS2019 x64、兼容的 OpenCV 环境包、GITS 账号、缺陷 ONNX 模型及授权测试图。提供的示例不包含相机采集、OK/NG 判定、PLC 通信或自动剔除。

## 2. 准备独立工程

以下命令在本仓库根目录的 CMD 执行：

```cmd
mkdir D:\gits-cases
xcopy examples\yolo-edge D:\gits-cases\defect-detection\ /E /I
copy docs\案例库\工业瑕疵检测\setup.manifest D:\gits-cases\defect-detection\setup.manifest
cd /d D:\gits-cases\defect-detection
mkdir models
mkdir images
```

把实际缺陷模型放到 `models/defects.onnx`，缺陷图放到 `images/ng.jpg`，正常图放到 `images/ok.jpg`。同时保留模型的类别表和期望标注。

## 3. 同步环境并构建

[setup.manifest](setup.manifest) 内容为：

```ini
[VS2019]
opencv==4.5.4: copy bin/* to ./workspace/
```

确认管理员提供的包和模型兼容后，在案例工程根目录执行：

```cmd
gis update --lean -m setup.manifest --no-obj
gis status --lean -m setup.manifest
where /r D:\lean\opencv@4.5.4@VS2019 OpenCVConfig.cmake
cmake -S . -B build -G "Visual Studio 16 2019" -A x64 -DOpenCV_DIR=D:/lean/opencv@4.5.4@VS2019/lib
cmake --build build --config Release
```

缓存位置、OpenCV 版本或配置目录不同，就修改相应参数与清单。前期本机 4.5.4 包的 CUDA 依赖存在不匹配，处理方法见快速入门，不能据此宣称该构建已在目标设备通过。

## 4. 执行与检查

仍在案例工程根目录执行：

```cmd
workspace\Release\yolo_edge.exe models\defects.onnx images\ng.jpg workspace\ng-result.jpg
workspace\Release\yolo_edge.exe models\defects.onnx images\ok.jpg workspace\ok-result.jpg
```

核对输出图、类别 ID 和缺陷框。缺陷图应与实际标注对应，正常图用于检查误报。程序处理一张图片后退出，没有后台服务需要停止。

环境同步通过不代表检测效果合格。上线前覆盖不同缺陷大小、曝光、反光、位置和正常样品，并记录实际准确性及延迟。

## 5. 故障与回退

- 缺 DLL：检查 workspace 及程序旁的 DLL、x64 架构和运行库。
- 模型加载失败：核对 ONNX 导出格式及 OpenCV 算子支持。
- 框或类别错误：核对模型输出契约和类别表，不要仅更改文件扩展名。
- 新包验证失败：保留该版本日志，在独立工程用上一份经过验收的 manifest、模型和程序重新复测。

## 6. 正式案例还需补齐

实际模型与类别表、授权 OK/NG 数据、判定阈值与模块、设备信息、构建记录、输入输出样例和验收结果。若要形成产线完整解决方案，还需相机、PLC 和异常人工处理流程。

[返回案例库](../README.md) · [命令参考](../../03-命令与配置参考.md)
