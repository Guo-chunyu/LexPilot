# LexPilot 未签名桌面安装包设计

## 目标

为非技术试用者提供 Windows 和 macOS 双击启动的安装产物，同时保留 Streamlit 现有界面、附件解析与本地规则流程。安装包不得包含开发者密钥或用户案件材料。

## 方案

`desktop/launcher.py` 作为唯一桌面入口。它在当前用户的应用数据目录创建附件、模型缓存、日志和可选配置文件，检测已有健康实例，分配本机端口，启动打包后的 Streamlit，并自动打开浏览器。重复双击时复用已有实例。

PyInstaller 在各目标系统生成 one-folder 运行目录。Windows 使用 Inno Setup 生成当前用户级安装程序、开始菜单项、桌面快捷方式和卸载入口。macOS 使用 PyInstaller `BUNDLE` 生成 `.app`，再由系统 `hdiutil` 生成包含应用、Applications 快捷方式和首次打开说明的 `.dmg`。

GitHub Actions 在 Windows x64、macOS arm64 和 macOS Intel 原生运行器上构建。手动运行工作流时保留可下载 artifacts；推送 `v*` 标签时额外创建或更新 GitHub Release。

## 信任与分发边界

本阶段不配置 Microsoft Authenticode、Apple Developer ID 或 Apple notarization。安装程序明确标为 `unsigned` 并附首次打开指引。Windows SmartScreen 和 macOS Gatekeeper 可能要求试用者执行一次确认操作。后续获得证书后，可在现有构建流程中增加签名步骤，无需改变应用数据模型。

## 验证

启动器单元测试覆盖系统数据目录、设置优先级、PyInstaller 资源定位和已有服务健康检查。Windows 构建后执行静默试装、启动健康检查和卸载验证。macOS 脚本由 GitHub 原生运行器生成两个架构的 DMG；Windows 本机只能做脚本与工作流静态校验。
