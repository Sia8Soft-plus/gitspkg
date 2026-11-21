# 安全帽识别

状态：待业务模型和现场验收。本文提供单图目标检测步骤，人员与安全帽关联、视频时序和告警尚需业务实现，不能单独作为人员安全保障系统。

## 1. 目标与资源

输入现场图片，输出人员、安全帽或训练模型定义的其他类别。使用 [YOLO C++ 单图工程](../../../examples/yolo-edge/README.md)，模型格式与构建要求见 [快速入门](../../01-快速入门.md)。

自行准备可用的业务 ONNX 模型、类别表、授权现场图片和管理员确认兼容的环境包。检测到一顶帽子，不等于所有人都佩戴安全帽。

## 2. 准备独立工程

在本仓库根目录 CMD 执行：

```cmd
mkdir D:\gits-cases
xcopy examples\yolo-edge D:\gits-cases\helmet-detection\ /E /I
copy docs\案例库\安全帽识别\setup.manifest D:\gits-cases\helmet-detection\setup.manifest
cd /d D:\gits-cases\helmet-detection
mkdir models
mkdir images
```

将模型放到 `models/helmet.onnx`，测试图放到 `images/site.jpg`。

## 3. 同步环境并构建

本案例 [setup.manifest](setup.manifest) 固定 VS2019 / OpenCV 4.5.4，与单图示例一致。在案例工程根目录执行：

```cmd
gis update --lean -m setup.manifest --no-obj
gis status --lean -m setup.manifest
where /r D:\lean\opencv@4.5.4@VS2019 OpenCVConfig.cmake
cmake -S . -B build -G "Visual Studio 16 2019" -A x64 -DOpenCV_DIR=D:/lean/opencv@4.5.4@VS2019/lib
cmake --build build --config Release
```

按实际缓存目录、包版本和 SDK 调整参数；前期 OpenCV 包的 CUDA 不匹配问题见快速入门。

## 4. 执行与检查

在案例工程根目录执行：

```cmd
workspace\Release\yolo_edge.exe models\helmet.onnx images\site.jpg workspace\helmet-result.jpg
```

检查数值类别 ID 与类别表、检测框位置和输出图片。程序完成单图后退出。验收数据应覆盖遮挡、背对镜头、远处人员、手持帽子、相似颜色物品和光照变化。

视频和告警项目还要验证人员与帽子的关联、连续帧判定、重复告警抑制、断流故障状态和恢复逻辑。不要把无检测结果自动解释为全员合规。

## 5. 故障与回退

无法加载模型先核对格式与 OpenCV 兼容性；缺 DLL 检查复制结果与架构。效果异常先确认模型标签和现场数据，不要将环境同步成功当成业务通过。

更换模型或依赖时，在独立工程复测；保留上一份已验收的包清单、模型、配置和程序用于回退。

## 6. 正式案例还需补齐

模型与数据来源、类别表、人员关联和时序模块、告警协议与源码、现场设备、输入输出样例及实际验收记录。

[返回案例库](../README.md) · [命令参考](../../03-命令与配置参考.md)
