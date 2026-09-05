param(
    [string]$Installer = "release\LexPilot-Windows-x64-Setup-unsigned.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installerPath = (Resolve-Path (Join-Path $projectRoot $Installer)).Path
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$installDir = [IO.Path]::GetFullPath(
    (Join-Path $tempRoot ("LexPilot-Smoke-" + [guid]::NewGuid().ToString("N")))
)
if (-not $installDir.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "试装目录不在系统临时目录中。"
}

$setup = Start-Process -FilePath $installerPath -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=$installDir"
) -Wait -PassThru
if ($setup.ExitCode -ne 0) { throw "安装程序退出码：$($setup.ExitCode)" }

$appExe = Join-Path $installDir "LexPilot.exe"
$uninstaller = Join-Path $installDir "unins000.exe"
if (-not (Test-Path -LiteralPath $appExe)) { throw "试装后找不到 LexPilot.exe。" }
$startedAt = Get-Date
$app = Start-Process -FilePath $appExe -ArgumentList "--smoke-test" -Wait -PassThru
$resultFile = Join-Path $env:LOCALAPPDATA "LexPilot\smoke-test.json"
if (-not (Test-Path -LiteralPath $resultFile)) { throw "桌面应用未写入健康检查结果。" }
$resultItem = Get-Item -LiteralPath $resultFile
if ($resultItem.LastWriteTime -lt $startedAt.AddSeconds(-2)) { throw "健康检查结果没有更新。" }
$result = Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json
if ($app.ExitCode -ne 0 -or -not $result.healthy) {
    throw "桌面应用健康检查失败：$($result | ConvertTo-Json -Compress)"
}

$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
) -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw "卸载程序退出码：$($uninstall.ExitCode)" }
if (Test-Path -LiteralPath $installDir) { throw "卸载后试装目录仍然存在。" }

Write-Output "Windows installer smoke test passed on port $($result.port)."
