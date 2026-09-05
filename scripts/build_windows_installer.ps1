param(
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9]+)*$')]
    [string]$Version = "0.1.0-dev",
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = (Get-Command python -ErrorAction Stop).Source
}

Push-Location $projectRoot
try {
    if (-not $SkipDependencies) {
        & $pythonExe -m pip install -r "desktop\requirements-desktop.txt"
        if ($LASTEXITCODE -ne 0) { throw "桌面构建依赖安装失败。" }
    }

    $env:LEXPILOT_VERSION = $Version
    & $pythonExe -m PyInstaller --noconfirm --clean "desktop\lexpilot.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

    $isccCandidates = @(
        (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $isccExe = $isccCandidates | Select-Object -First 1
    if (-not $isccExe) {
        throw "没有找到 Inno Setup 6。请先运行：winget install --id JRSoftware.InnoSetup --exact"
    }

    & $isccExe "/Qp" "/DMyAppVersion=$Version" "desktop\windows\LexPilot.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup 安装包构建失败。" }

    $installer = Join-Path $projectRoot "release\LexPilot-Windows-x64-Setup-unsigned.exe"
    if (-not (Test-Path -LiteralPath $installer)) { throw "未生成预期安装包：$installer" }
    Get-Item -LiteralPath $installer | Select-Object FullName, Length, LastWriteTime
}
finally {
    Pop-Location
}
