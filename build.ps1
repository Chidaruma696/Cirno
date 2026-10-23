# Compila Cirno en Windows: crea .venv, instala dependencias, genera dist\Cirno\ con PyInstaller
# y el instalador dist\Cirno-X.Y.Z-setup.exe con Inno Setup 6.
#
#   .\build.ps1                 # todo
#   .\build.ps1 -SinInstalador  # solo dist\Cirno\Cirno.exe
#   .\build.ps1 -Limpiar        # borra build\ y dist\ antes de empezar

param(
    [switch]$SinInstalador,
    [switch]$Limpiar
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Los programas nativos (pip, PyInstaller, ISCC) escriben su registro por stderr y PowerShell 5.1
# lo convierte en errores si la salida va redirigida; se ejecutan vía cmd para unir ambas salidas.
function Invoke-Nativo([string]$Comando) {
    cmd /c "$Comando 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "Falló: $Comando" }
}

if ($Limpiar) {
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creando .venv..."
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv } else { python -m venv .venv }
}
$python = ".\.venv\Scripts\python.exe"

Write-Host "Instalando dependencias..."
Invoke-Nativo "$python -m pip install --quiet --upgrade pip"
Invoke-Nativo "$python -m pip install --quiet -r requirements.txt"

$version = (Select-String -Path "cirno\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Cirno ${version}: PyInstaller..."
Invoke-Nativo "$python -m PyInstaller --noconfirm --clean --log-level WARN cirno.spec"

if ($SinInstalador) {
    Write-Host "Listo: dist\Cirno\Cirno.exe"
    exit 0
}

$candidatos = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $candidatos | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    throw "No se encontró Inno Setup 6 (ISCC.exe). Instálalo desde https://jrsoftware.org/isdl.php o usa -SinInstalador."
}

Write-Host "Inno Setup..."
Invoke-Nativo "`"$iscc`" /Q /DMyAppVersion=$version installer\Cirno.iss"

Write-Host "Listo: dist\Cirno-$version-setup.exe"
