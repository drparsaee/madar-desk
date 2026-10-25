[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$MainExe,
 [Parameter(Mandatory=$true)][string]$AccountingExe,
 [Parameter(Mandatory=$true)][string]$WebView2Installer,
 [Parameter(Mandatory=$true)][string]$DestinationFolder,
 [switch]$AccountingRecoveryUI
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$dest=[IO.Path]::GetFullPath($DestinationFolder)
if (Test-Path $dest) { throw 'New package destination required; refusing overwrite.' }
if (!(Test-Path -LiteralPath $MainExe) -or !(Test-Path -LiteralPath $AccountingExe) -or
    !(Test-Path -LiteralPath $WebView2Installer)) { throw 'Missing source executable or prerequisite.' }
$parent=Split-Path -Parent $dest
[void][IO.Directory]::CreateDirectory($parent)
$apps=Join-Path $dest 'Apps'
$prereqs=Join-Path $dest 'Prerequisites'
[void][IO.Directory]::CreateDirectory($apps)
[void][IO.Directory]::CreateDirectory($prereqs)
Copy-Item -LiteralPath $MainExe -Destination (Join-Path $apps 'Madar-Desk.exe')
Copy-Item -LiteralPath $AccountingExe -Destination (Join-Path $apps 'Madar-Accounting.exe')
Copy-Item -LiteralPath $WebView2Installer -Destination (Join-Path $prereqs 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'madar_suite_setup.ps1') -Destination (Join-Path $dest 'Setup.ps1')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README_MADAR_INSTALL_FA.txt') -Destination (Join-Path $dest 'راهنمای نصب.txt')
$manifest=[ordered]@{
    package='Madar-Suite-Windows-x64'
    schema=1
    createdUtc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    apps=@{
       madarSha256=(Get-FileHash -LiteralPath (Join-Path $apps 'Madar-Desk.exe') -Algorithm SHA256).Hash
       accountingSha256=(Get-FileHash -LiteralPath (Join-Path $apps 'Madar-Accounting.exe') -Algorithm SHA256).Hash
    }
    appCapabilities=@{
       accountingRecoveryUI=[bool]$AccountingRecoveryUI
    }
    prerequisites=@{
       webview2Sha256=(Get-FileHash -LiteralPath (Join-Path $prereqs 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe') -Algorithm SHA256).Hash
       webview2Source='https://go.microsoft.com/fwlink/?linkid=2124701'
    }
}
($manifest | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath (Join-Path $dest 'manifest.json') -Encoding UTF8
$setup=@'
@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Existing user data was not modified.
  pause
  exit /b 1
)
echo Installation complete.
pause
'@
[IO.File]::WriteAllText((Join-Path $dest 'INSTALL.cmd'),$setup,[Text.Encoding]::ASCII)
Write-Host ('PACKAGE_CREATED '+$dest)
