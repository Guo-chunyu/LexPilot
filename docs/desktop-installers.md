# LexPilot 桌面安装包

## 给试用者的文件

- Windows 10/11 x64：`LexPilot-Windows-x64-Setup-unsigned.exe`
- Apple 芯片 Mac（M1/M2/M3/M4 等）：`LexPilot-macOS-Apple-Silicon-arm64-unsigned.dmg`
- Intel 芯片 Mac：`LexPilot-macOS-Intel-x64-unsigned.dmg`

GitHub Actions 暂不可用时，也可以运行 `python scripts/build_manual_release_archives.py --version 0.1.0`，生成可手动上传的 Windows ZIP 和 Intel/Apple 芯片通用 Mac ZIP。Mac ZIP 使用双击安装脚本，在朋友的 Mac 上联网下载隔离的 Python 3.12 与运行依赖，再创建 `~/Applications/LexPilot.app`。

Windows 安装程序会安装到当前用户目录并创建开始菜单和桌面快捷方式，不要求管理员权限。Mac 用户打开对应 DMG 后，将 `LexPilot.app` 拖入“应用程序”。两种系统双击 LexPilot 都会启动本机服务并自动打开默认浏览器。

## 未签名版首次启动

这些试用包没有 Microsoft/Apple 商业代码签名，也没有经过 Apple 公证。Windows SmartScreen 出现提示时，点击“更多信息”，核对名称后选择“仍要运行”。macOS 请在“应用程序”中按住 Control 点击 LexPilot，选择“打开”；若仍被阻止，到“系统设置 → 隐私与安全性”点击“仍要打开”。

## 数据与可选模型配置

安装包不携带任何 API 密钥。应用没有密钥时继续使用本地规则流程。上传材料、日志和可选设置保存在：

- Windows：`%LOCALAPPDATA%\LexPilot`
- macOS：`~/Library/Application Support/LexPilot`

如需启用可选语义模型，退出应用，编辑该目录内自动生成的 `settings.env`，填入使用者自己的 `DASHSCOPE_API_KEY` 后重启。不要共享或提交该文件。

## 本机构建

Windows PowerShell：

```powershell
winget install --id JRSoftware.InnoSetup --exact
.\scripts\build_windows_installer.ps1 -Version 0.1.0
```

macOS 终端：

```bash
bash desktop/macos/build_dmg.sh 0.1.0
```

构建结果写入 `release/`。PyInstaller 必须在目标系统上运行，因此 Windows 不能直接生成可用的 macOS `.app`；仓库中的 GitHub Actions 会分别使用 Windows、Apple Silicon Mac 和 Intel Mac 构建原生安装包。

Windows 构建会在上传前自动静默试装，启动本机服务、检查健康页和首页，再执行卸载。macOS 构建由对应架构的原生运行器完成并上传 DMG。
