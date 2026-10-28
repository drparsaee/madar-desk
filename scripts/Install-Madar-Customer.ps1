# Installs one immutable Madar executable version, retaining the user's data.
# Does not run automatically. All defaults are per-user (no elevation).
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\MadarDesk'),
    [string]$DataRoot = (Join-Path $env:APPDATA 'MadarDesk'),
    [string]$BackupRoot = (Join-Path $env:LOCALAPPDATA 'MadarDesk-ReleaseBackups'),
    [string]$PackageRoot = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
$version = '1.0.0'
$exeName = 'Madar-Desk-v1.0.0-Customer-20261028.exe'
$manifestPath = Join-Path $PackageRoot 'Madar-Release-Manifest.json'
$source = Join-Path $PackageRoot $exeName

function Resolve-FullPath([string]$value) {
    return [IO.Path]::GetFullPath($value).TrimEnd([IO.Path]::DirectorySeparatorChar)
}
function Assert-NotWithin([string]$first, [string]$second) {
    if ($first.Equals($second,[StringComparison]::OrdinalIgnoreCase) -or
        $first.StartsWith($second + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw ('Unsafe overlapping installation/data/backup paths: '+$first+' / '+$second)
    }
}
function Assert-NoLinks([string]$folder) {
    $items = @(Get-Item -LiteralPath $folder -Force)
    $items += @(Get-ChildItem -LiteralPath $folder -Recurse -Force -ErrorAction Stop)
    foreach ($item in $items) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw ('A linked or junction path in data prevents safe update: '+$item.FullName)
        }
    }
}

$InstallRoot = Resolve-FullPath $InstallRoot
$DataRoot = Resolve-FullPath $DataRoot
$BackupRoot = Resolve-FullPath $BackupRoot
$PackageRoot = Resolve-FullPath $PackageRoot
Assert-NotWithin $InstallRoot $DataRoot
Assert-NotWithin $DataRoot $InstallRoot
Assert-NotWithin $BackupRoot $DataRoot
Assert-NotWithin $DataRoot $BackupRoot
Assert-NotWithin $BackupRoot $InstallRoot
Assert-NotWithin $InstallRoot $BackupRoot
Assert-NotWithin $PackageRoot $DataRoot
Assert-NotWithin $DataRoot $PackageRoot

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Madar executable missing from package.' }
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Release manifest missing.' }
$manifest = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
if ($manifest.version -cne $version -or $manifest.executable -cne $exeName -or
    $manifest.sha256 -cnotmatch '^[0-9a-fA-F]{64}$') {
    throw 'Invalid package version or manifest.'
}
$sha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
if ($sha -ine $manifest.sha256) { throw 'Package integrity check failed.' }

# A closed app is essential for a consistent on-disk snapshot. A headless
# service can still be a writer when no main window is visible.
$running = @(Get-Process -ErrorAction Stop | Where-Object {
    $_.ProcessName -like 'Madar-Desk*' -or $_.ProcessName -eq 'MadarHost'
})
if ($running.Count -gt 0) { throw 'Close Madar Desk and MadarHost before installing or updating.' }
$service = Get-Service -Name 'MadarHost' -ErrorAction SilentlyContinue
if ($null -ne $service -and $service.Status -eq 'Running') {
    throw 'Stop MadarHost service before installing or updating.'
}

$versions = Join-Path $InstallRoot 'versions'
$targetDir = Join-Path $versions $version
$target = Join-Path $targetDir 'Madar-Desk.exe'
$pointer = Join-Path $InstallRoot 'current-version.txt'
$existingTarget = Test-Path -LiteralPath $target
if ($existingTarget) {
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ine $sha) {
        throw 'Different executable already exists for this version; refusing overwrite.'
    }
}
if (Test-Path -LiteralPath $pointer -PathType Leaf) {
    $previousVersion = (Get-Content -LiteralPath $pointer -Raw).Trim()
    if ($previousVersion -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
        throw 'Invalid current-version pointer; manual recovery required.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $versions ($previousVersion+'\Madar-Desk.exe')) -PathType Leaf)) {
        throw 'Existing installation is incomplete; manual recovery required.'
    }
}

# One full-profile snapshot BEFORE switching executable versions. This archive
# includes attachments, settings, identity and finance. It contains private data.
$snapshot = $null
if (Test-Path -LiteralPath $DataRoot -PathType Container) {
    Assert-NoLinks $DataRoot
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fffffff')
    $snapshot = Join-Path $BackupRoot ('Madar-Profile-Before-'+$version+'-'+$stamp+'.zip')
    [IO.Compression.ZipFile]::CreateFromDirectory($DataRoot, $snapshot, [IO.Compression.CompressionLevel]::Optimal, $false)
    try {
        $archive = [IO.Compression.ZipFile]::OpenRead($snapshot)
        try {
            $entries = @($archive.Entries | Where-Object { $_.Name -ne '' })
            $files = @(Get-ChildItem -LiteralPath $DataRoot -File -Recurse -Force)
            if ($entries.Count -ne $files.Count) { throw 'Profile archive file count mismatch.' }
            foreach ($file in $files) {
                $relative = $file.FullName.Substring($DataRoot.Length+1).Replace('\','/')
                $found = @($entries | Where-Object { $_.FullName.Replace('\','/') -ceq $relative })
                if ($found.Count -ne 1 -or $found[0].Length -ne $file.Length) {
                    throw ('Profile snapshot verification failed for '+$relative)
                }
            }
        } finally { $archive.Dispose() }
    } catch {
        throw ('Profile snapshot validation failed. Existing data not changed. '+$_.Exception.Message)
    }
}

New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
if (-not $existingTarget) {
    $tempExe = Join-Path $targetDir ('Madar-Desk-'+[guid]::NewGuid().ToString('N')+'.tmp')
    try {
        Copy-Item -LiteralPath $source -Destination $tempExe -ErrorAction Stop
        if ((Get-FileHash -LiteralPath $tempExe -Algorithm SHA256).Hash -ine $sha) { throw 'Staged EXE hash mismatch.' }
        Move-Item -LiteralPath $tempExe -Destination $target -ErrorAction Stop
    } finally {
        if (Test-Path -LiteralPath $tempExe) { Remove-Item -LiteralPath $tempExe -Force }
    }
}

# The pointer is the only switched runtime resource. Older binaries stay.
$pointerTmp = Join-Path $InstallRoot ('current-version-'+[guid]::NewGuid().ToString('N')+'.tmp')
try {
    [IO.File]::WriteAllText($pointerTmp, $version + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $pointer) {
        [IO.File]::Replace($pointerTmp, $pointer, (Join-Path $InstallRoot 'previous-version.txt'))
    } else {
        Move-Item -LiteralPath $pointerTmp -Destination $pointer
    }
} finally {
    if (Test-Path -LiteralPath $pointerTmp) { Remove-Item -LiteralPath $pointerTmp -Force }
}
$runScript = Join-Path $InstallRoot 'Run-Madar.cmd'
$launcher = @'
@echo off
setlocal
set /p MADAR_VERSION=<"%~dp0current-version.txt"
if "%MADAR_VERSION%"=="" exit /b 1
start "" "%~dp0versions\%MADAR_VERSION%\Madar-Desk.exe"
endlocal
'@
[IO.File]::WriteAllText($runScript, $launcher, [Text.Encoding]::ASCII)
# Shortcuts are created only for the opt-in default per-user install.
if ($InstallRoot -ieq (Resolve-FullPath (Join-Path $env:LOCALAPPDATA 'Programs\MadarDesk'))) {
    $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $startMenu 'مدار.lnk'))
    $shortcut.TargetPath = $runScript
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.IconLocation = $target + ',0'
    $shortcut.Save()
}
Write-Output ('INSTALLED: '+$target)
Write-Output ('LAUNCHER: '+$runScript)
Write-Output ('DATA: '+$DataRoot+' (not moved or overwritten)')
if ($snapshot) { Write-Output ('PRE-UPDATE FULL PROFILE BACKUP: '+$snapshot) }
