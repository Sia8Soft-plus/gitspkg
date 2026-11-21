# VisionEngine 边缘推理环境部署

状态：依据已有包使用记录整理，当前仅提供包同步与交付目录准备，尚缺完整业务依赖、启动配置和设备验收记录。

## 1. 目标与前置条件

将 VisionEngine、YOLO 推理算子、MQTT 和 Redis 组件同步到独立部署目录。环境包名称和版本参考既有使用记录，管理员需确认目标 Server / Windows / VS2019 下确有对应文件及正确依赖。

还需实际项目的启动和停止脚本、模型、配置、硬件 SDK、DLL 运行库及测试输入。提供的 CLI 和管理端文档没有规定 VisionEngine 的模型配置格式或启动参数，本文不猜测这些接口。

## 2. 在管理端核对包

1. 进入“我的 Lean”，选择实际 Server、操作系统和编译器。
2. 核对 [setup.manifest](setup.manifest) 中各包的名称、版本和稳定版状态。
3. 核对需要保留的完整依赖清单，特别是 Qt、CUDA、libtorch 和其他业务组件。
4. 发布有变更的包后等待后台任务成功，再交给只读账号下载。

服务器包维护流程见 [进阶教程](../../02-进阶教程.md)。本清单不是已证明完整的依赖闭包，不能据此省略项目实际需要的其他包。

## 3. 准备独立部署目录

以下在本仓库根目录 CMD 执行：

```cmd
mkdir D:\gits-cases
mkdir D:\gits-cases\visionengine
copy docs\案例库\VisionEngine边缘部署\setup.manifest D:\gits-cases\visionengine\setup.manifest
cd /d D:\gits-cases\visionengine
```

清单内容：

```ini
[VS2019]
VisionEngine-remote==1.1.26.7: copy bin/* to ./workspace/
CInference-yolov11-libtorch==1.0.26.0118: copy bin/* to ./workspace/
mosquitto-Service==2.0.22: copy bin/* to ./services/mosquitto/
Redis_x64-Service==5.0.14.1: copy bin/* to ./services/Redis_x64/
```

在这个部署目录执行：

```cmd
gis update --lean -m setup.manifest --no-obj
gis status --lean -m setup.manifest
```

检查 unresolved、missing、待更新计数和所有 copy 结果，不允许把其他编译器的回退包视为目标包验证通过。

## 4. 核对交付目录并启动业务

预期形成：

```text
visionengine/
  setup.manifest
  workspace/
  services/
    mosquitto/
    Redis_x64/
```

按实际项目说明补齐模型、配置和剩余组件。然后使用**部署团队提供的实际启动脚本**加载算子与模型、启动服务；停止时使用该项目对应的停止流程。`gis update` 不自动注册或启动这些业务服务。

当前缺少可公开的启动参数和配置样例，所以本节尚不能完成一键运行演示。

## 5. 验收与故障处理

- 核对正确版本、编译器和运行库，确认业务进程能启动。
- 通过加载日志确认模型和算子实际成功加载，用一组已知输入检查真实输出。
- 使用 MQTT/Redis 的项目，核对实际服务配置、认证和测试事件；不要只检查目录存在。
- 日志缺 DLL 时定位对应包和 ABI；启动失败时保留原始业务日志。
- 重启或断网后验证业务恢复。需要回退时使用上一份经过验收的完整发行包及配置；旧版部署保存在独立目录。

## 6. 正式案例还需补齐

完整 manifest、启动/停止脚本、模型和配置样例、硬件 SDK 与设备、真实输入输出、服务设置和实测记录。补齐后才能将本案例从“环境准备”升级为“完整部署方案”。

[返回案例库](../README.md) · [命令参考](../../03-命令与配置参考.md)
