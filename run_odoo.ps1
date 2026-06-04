param(
    [string]$Version = "19.0",
    [string]$Config,
    [string]$Port = "8069",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$OdooArgs
)

$ErrorActionPreference = "Stop"

$RootPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$VersionPath = Join-Path $RootPath "versions\$Version"
$VenvPython = Join-Path $VersionPath "venv\Scripts\python.exe"
$OdooServer = Join-Path $VersionPath "odoo-server"
$OdooBin = Join-Path $OdooServer "odoo-bin"
$ConfigPath = if ($Config) { $Config } else { Join-Path $VersionPath "odoo.conf" }
$DataDir = Join-Path $VersionPath "data"

$CoreAddons = Join-Path $OdooServer "addons"
$VersionAddons = Join-Path $VersionPath "custom_addons"
$SharedAddons = Join-Path $RootPath "custom_addons"

$AddonsPaths = @()
if (Test-Path $CoreAddons) {
    $AddonsPaths += $CoreAddons
}
if ((Test-Path $VersionAddons) -and (Get-ChildItem $VersionAddons -Force | Select-Object -First 1)) {
    $AddonsPaths += $VersionAddons
}
if (Test-Path $SharedAddons) {
    $AddonsPaths += $SharedAddons
}

$RequiredPaths = @{
    "virtualenv Python" = $VenvPython
    "odoo-bin" = $OdooBin
    "Odoo config" = $ConfigPath
    "Odoo server" = $OdooServer
    "data directory" = $DataDir
}

foreach ($Item in $RequiredPaths.GetEnumerator()) {
    if (-not (Test-Path $Item.Value)) {
        Write-Error "Missing $($Item.Key): $($Item.Value)"
        exit 1
    }
}

$CommandArgs = @(
    $OdooBin,
    "-c", $ConfigPath,
    "--addons-path", ($AddonsPaths -join ","),
    "--http-port", $Port,
    "--data-dir", $DataDir
)

if ($OdooArgs) {
    $CommandArgs += $OdooArgs
}

Write-Host "Running Odoo $Version"
Write-Host "Config: $ConfigPath"
Write-Host "Addons: $($AddonsPaths -join ',')"
Write-Host "URL: http://localhost:$Port"
Write-Host ""

Push-Location $OdooServer
try {
    & $VenvPython @CommandArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
