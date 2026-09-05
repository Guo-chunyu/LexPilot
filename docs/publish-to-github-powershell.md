# 用 Windows PowerShell 发布到 GitHub

以下命令在项目目录 `W:\YOUAN_app\Law_Company_Agent-main` 中执行。当前目录还不是 Git 仓库，但电脑已经安装 Git 并配置了提交者姓名和邮箱。

## 1. 初始化并完成首次提交

```powershell
Set-Location "W:\YOUAN_app\Law_Company_Agent-main"

git init
git branch -M main
git add .
git status
git commit -m "Build LexPilot legal consultation app and desktop installers"
```

运行 `git status` 时，应确认 `.env`、`.local_data`、`.venv`、`build`、`dist` 和 `release` 没有进入待提交文件。这些目录已由 `.gitignore` 排除。

## 2. 安装并登录 GitHub CLI

```powershell
winget install --id GitHub.cli --exact
```

安装完成后重新打开一个 PowerShell 窗口，再运行：

```powershell
gh auth login
```

按提示选择 `GitHub.com`、`HTTPS` 和浏览器登录。

## 3. 创建 GitHub 仓库并推送

公开仓库：

```powershell
Set-Location "W:\YOUAN_app\Law_Company_Agent-main"
gh repo create LexPilot --public --source . --remote origin --push
```

如果只想让指定朋友访问，将 `--public` 改成 `--private`，然后在 GitHub 仓库的 Settings → Collaborators 中邀请他们。

## 4. 创建首个安装包版本

```powershell
git tag v0.1.0
git push origin v0.1.0
```

标签推送后，GitHub Actions 会分别构建 Windows x64、Apple Silicon Mac 和 Intel Mac 安装包。进入仓库的 Actions 页面查看进度；三个构建成功后，安装文件会出现在仓库右侧 Releases 的 `v0.1.0` 中。

## 后续更新

```powershell
Set-Location "W:\YOUAN_app\Law_Company_Agent-main"
git add .
git status
git commit -m "Describe the update"
git push

git tag v0.1.1
git push origin v0.1.1
```

每次推送新的 `v*` 标签都会创建对应 Release。不要重复使用已经发布的版本号。
