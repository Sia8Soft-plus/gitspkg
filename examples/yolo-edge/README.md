# YOLO C++ 单图示例

按 [5 分钟快速入门](../../docs/01-快速入门.md) 同步 OpenCV、构建并运行。本目录仅提供工程与代码，不含模型、图片或 SDK。

支持经过兼容性验证的固定 640x640、batch=1、无 NMS 的 YOLOv8/YOLO11 检测输出 `[1,4+C,N]` 或 `[1,N,4+C]`，C 为类别数。假设预测点数量大于属性数；不自动识别 YOLOv5/objectness 或端到端 NMS 输出。错误模型有时具有同形状输出，仍需使用者核对模型契约。

预处理为居中 letterbox、BGR 转 RGB 和除以 255；后处理使用类别分数及逐类 NMS，输出数值类别 ID。CPU 后端，不含视频、跟踪、告警或硬件优化。

```text
models/yolo.onnx       # Supply an authorized model.
images/input.jpg       # Supply an authorized image.
workspace/result.jpg  # Generated result.
```

`setup.manifest` 引用已有使用记录中的 OpenCV 4.5.4；该版本未必能执行所有新 YOLO 导出图，先验证模型算子兼容性，必要时请求管理员发布较新 OpenCV 或兼容模型。首次构建前以实际包里的 `OpenCVConfig.cmake` 定位 `OpenCV_DIR`，同时核对编译器和运行库。缺少模型或包时不能宣称推理已验证。

本机该 OpenCV 包的 CMake 配置要求 CUDA 11.2，而当前找到 11.0，配置阶段会失败。CPU DNN 后端不会改变包的二进制依赖；优先申请 CPU-only 包，或补齐该包要求的 SDK。当前仅完成 OpenCV 头文件下的 C++17 语法检查，未完成真实链接和模型推理。
