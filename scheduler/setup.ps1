$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Write-Host "[SETUP] project=$root"

function Fail([string]$Code, [string]$Message, [string]$Hint) {
    throw "[$Code] $Message`nhint: $Hint"
}

function Invoke-Checked([string]$FilePath, [string[]]$ArgumentList, [string]$Label) {
    Write-Host "[SETUP] $Label"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        Fail "SETUP_COMMAND_FAILED" "$Label failed with exit code $LASTEXITCODE" "查看上方命令输出；网络下载卡住时切换网络后重跑 scheduler\setup.cmd"
    }
}

$py64 = $null
$py64Args = @()
try {
    & py -3.12 -c "import struct,sys; assert struct.calcsize('P')*8==64; print(sys.executable)" | Out-Null
    if ($LASTEXITCODE -eq 0) { $py64 = "py"; $py64Args = @("-3.12") }
} catch {}

if (-not $py64) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import struct,sys; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')*8==64" | Out-Null
        if ($LASTEXITCODE -eq 0) { $py64 = $python.Source; $py64Args = @() }
    }
}
if (-not $py64) { Fail "PYTHON64_MISSING" "未找到 64 位 Python 3.12" "安装 64 位 Python 3.12 后重跑 scheduler\setup.cmd" }

Invoke-Checked $py64 ($py64Args + @("-m","pip","install","-r",(Join-Path $root "requirements.txt"))) "install 64-bit dependencies"

$py32Exe = $null
$py32BaseArgs = @()
try {
    & py -3.11-32 -c "import struct,sys; assert struct.calcsize('P')*8==32; print(sys.executable)" | Out-Null
    if ($LASTEXITCODE -eq 0) { $py32Exe = "py"; $py32BaseArgs = @("-3.11-32") }
} catch {}
if (-not $py32Exe) {
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311-32\python.exe"
    if (Test-Path -LiteralPath $candidate) {
        & $candidate -c "import struct,sys; assert sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==32" | Out-Null
        if ($LASTEXITCODE -eq 0) { $py32Exe = $candidate; $py32BaseArgs = @() }
    }
}
if (-not $py32Exe) {
    Fail "PYTHON32_MISSING" "未找到 32 位 Python 3.11" "安装 32 位 Python 3.11 后重跑 scheduler\setup.cmd"
}

$venvPython = Join-Path $root ".venv32\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-Checked $py32Exe ($py32BaseArgs + @("-m","venv",(Join-Path $root ".venv32"))) "create .venv32"
}
Invoke-Checked $venvPython @("-m","pip","install","--upgrade","pip") "upgrade .venv32 pip"
Invoke-Checked $venvPython @("-m","pip","install","--no-deps","jqktrader==0.1.3","easyutils==0.1.7") "install jqktrader/easyutils without dependency downgrade"
Invoke-Checked $venvPython @("-m","pip","install","-r",(Join-Path $root "execution\requirements32.txt")) "install 32-bit execution dependencies"

$exampleConfig = Join-Path $root "config\config.example.yaml"
$config = Join-Path $root "config\config.yaml"
if (-not (Test-Path -LiteralPath $config)) { Copy-Item -LiteralPath $exampleConfig -Destination $config }
$exampleSecrets = Join-Path $root "config\secrets.example.yaml"
$secrets = Join-Path $root "config\secrets.yaml"
if (-not (Test-Path -LiteralPath $secrets)) { Copy-Item -LiteralPath $exampleSecrets -Destination $secrets }

Write-Host "[SETUP] next: edit config/config.yaml and config/secrets.yaml, then run python run.py doctor"
Write-Host "[SETUP] done"
