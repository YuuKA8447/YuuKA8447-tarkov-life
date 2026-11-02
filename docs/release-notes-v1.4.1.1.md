# V1.4.1.1 构建工程化（2026-10-31）

本版只改构建链与内部诊断，不改识别、界面与按键行为。

## 版本号

按 `MAJOR.MINOR.PATCH.BUILD` 四段规则，本次属内容不变的重新打包，只递增第 4 位 BUILD：`1.4.1.0 → 1.4.1.1`。

## 主要改动

- 新增 `version.json` 作为版本号唯一真源，六个构建脚本与 `一键构建.bat` 全部改为读取它，BAT 中原先 8 处硬编码版本字面量已移除。
- 新增构建第 2 步 `check_version_sync.py`：版本不一致会在构建早期直接失败并列出全部位置，不必等到第 15 步才发现。
- 新增构建第 6 步 `check_marshal_sync.py`：源码改动未重建 `.marshal` 会在构建时被拦下。
- 34 处静默 `except: pass` 改为记录到 `startup.log`，按上下文 10 秒窗口、每类最多 3 条限流；诊断「某个功能没生效」时有据可查。
- `patch_monitor_extraction.py` 去掉三处硬编码字节偏移，改为按指令模式语义定位，母版或 Python 版本变化时明确报错而不是静默打错位置。
- 新增 `scripts\reference\monitor_reference.txt`：把无源码的 `monitor.marshal` 导出为可读的分组反汇编，只用于阅读，不参与构建。
- 构建步骤由 16 步增至 18 步。

## 未改动

识别模板、阈值、撤离状态机、Alt+F4 与自动按键行为、浮窗布局与锚点规则全部保持 V1.4.1.0 行为。`detector.marshal`、`monitor.marshal`、`sound_library.marshal` 的字节内容未变。

## 验证

- 50 张源图 + 7 条过曝切片回归、撤离状态机测试、`--smoke-test`、`validate_final` 全部通过。
- 版本校验与 marshal 校验均做了反向验证（故意改坏后确认失败、改回后确认通过）。
- 补丁改造等价性：从原始 `monitor.marshal` 重跑补丁链，67 个代码对象的指令序列与原文件逐条一致。
