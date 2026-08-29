# LAA（洛AA）

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 与
[MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate)
开发的《交错战线》自动化工具。

## 当前功能

- 开始游戏：按任务需要启动 MuMu 与游戏，并处理已知开屏页面。
- 竞技场：识别战力、按设置刷新和挑战、处理战斗与奖励页面。
- 周本：从多个中间页面接续，识别四种地图情况并执行对应路线。
- 基建-订单库：扫描自己与好友的固定订单栏位，按设置判断订单并支持缺少素材时自动合成。
- 操作录制器：保存截图、点击和拖拽记录，并支持特殊标注。

项目仍在持续开发中，当前版本属于开发预览版。功能效果依赖游戏界面、
分辨率、模拟器环境与识别资源，使用前请阅读发布说明并自行验证。

## 目录

- `agent/`：Python 自定义动作与任务流程。
- `assets/`：MFA 接口、Pipeline、OCR 和图像识别资源。
- `tools/`：录制器、诊断、测试和本地辅助工具。
- `docs/`：MaaPracticeBoilerplate 原始开发文档。
- `项目文档.md`：项目交接、页面逻辑和开发要求。

## 本地数据

以下内容只保存在本机，不进入 Git 仓库：

- `gui/`：MFAAvalonia 完整运行目录。
- `.venv/`：Python 虚拟环境。
- `record/`：录制截图和标注原始数据。
- `verification/`、`debug/`：验证截图与运行日志。
- `config/`：本机运行状态和用户设置。

可直接运行的完整版本应通过 GitHub Releases 发布，不应提交到源码历史。

## 发布说明

当前版本、已知限制和升级注意事项见 [RELEASE_NOTES.md](RELEASE_NOTES.md)。

## 隐私与安全

仓库不包含本机录制截图、运行日志、用户设置、模拟器数据或访问凭据。
提交问题时，请先检查日志和截图，避免公开账号、UID、邮箱等个人信息。

## 开发环境

当前开发环境以 Windows、MuMu 模拟器 12、Python 和 MFAAvalonia 为主。
详细路径、任务状态和行为要求见 `项目文档.md`。

## 致谢

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)
- [MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate)

## 开源协议

本项目沿用模板仓库的 [MIT License](LICENSE)。项目中的第三方组件、游戏素材
及相关商标仍分别归其权利人所有；MIT License 不授予这些第三方内容的权利。
