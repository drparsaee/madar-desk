# Madar dual-app Windows per-user offline installer. Does not touch old finance data.
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\Madar Suite'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'Madar Suite Data'),
    [switch]$Silent,
    [switch]$NoShortcuts,
    [switch]$SkipRuntimeForTest,
    [string]$TestShortcutRoot = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-AbsoluteLocal([string]$PathText) {
    if ($PathText -notmatch '^[A-Za-z]:[\\/]') {
        throw 'Local absolute drive paths only; network shares are not supported.'
    }
    $full = [IO.Path]::GetFullPath($PathText).TrimEnd('\')
    if ($full.Length -le 3) { throw 'Drive root is not a valid install location.' }
    $entry = $full
    while ($entry) {
        if ([IO.File]::Exists($entry) -or [IO.Directory]::Exists($entry)) {
            $attr = (Get-Item -LiteralPath $entry -Force).Attributes
            if (($attr -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw ('Junction/symlink directory is refused: '+$entry)
            }
        }
        $parent = [IO.Path]::GetDirectoryName($entry)
        if (!$parent -or $parent -eq $entry) { break }
        $entry=$parent
    }
    return $full
}
function Verify-Sha([string]$Path,[string]$Expected) {
    if (![IO.File]::Exists($Path)) { throw ('Required package file is missing: '+$Path) }
    $actual=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ine $Expected) { throw ('Checksum validation failed: '+$Path) }
}
function Get-WebView2Installed {
    $key='{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    foreach($location in @(
        ('Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\'+$key),
        ('Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\EdgeUpdate\Clients\'+$key),
        ('Registry::HKEY_CURRENT_USER\Software\Microsoft\EdgeUpdate\Clients\'+$key))) {
        try {
            $value=(Get-ItemProperty -LiteralPath $location -Name pv -ErrorAction Stop).pv
            if ($value -and $value -ne '0.0.0.0') { return $value }
        } catch {}
    }
    return $null
}
function Assert-NotRunning([string]$Filename) {
    foreach ($proc in Get-CimInstance Win32_Process -Filter "Name = '$Filename'" -ErrorAction SilentlyContinue) {
        if ($proc.ExecutablePath) { throw ('Close '+$Filename+' before installation.') }
    }
}

$payload=Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath=Join-Path $payload 'manifest.json'
if (!(Test-Path -LiteralPath $manifestPath)) { throw 'manifest.json is missing from installer folder.' }
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.package -ne 'Madar-Suite-Windows-x64' -or $manifest.schema -ne 1) {
    throw 'Invalid installer package manifest.'
}
if (!([Environment]::Is64BitOperatingSystem)) {
    throw 'This installer is for Windows x64 (Windows 10/11) only.'
}
$InstallRoot=Assert-AbsoluteLocal $InstallRoot
$DataRoot=Assert-AbsoluteLocal $DataRoot
if ($InstallRoot -eq $DataRoot -or $DataRoot.StartsWith($InstallRoot+'\',
        [StringComparison]::OrdinalIgnoreCase) -or
        $InstallRoot.StartsWith($DataRoot+'\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Program files and private accounting data MUST be in different directories.'
}
$source1=Join-Path $payload 'Apps\Madar-Desk.exe'
$source2=Join-Path $payload 'Apps\Madar-Accounting.exe'
$webView=Join-Path $payload 'Prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
Verify-Sha $source1 $manifest.apps.madarSha256
Verify-Sha $source2 $manifest.apps.accountingSha256
Verify-Sha $webView $manifest.prerequisites.webview2Sha256

if ($SkipRuntimeForTest) {
    if ($env:MADAR_INSTALL_QA -ne '1' -or !$Silent -or
        (!$NoShortcuts -and !$TestShortcutRoot)) {
        throw 'Skipping runtime is permitted only for isolated QA.'
    }
} else {
    $version=Get-WebView2Installed
    if (!$version) {
        $sig=Get-AuthenticodeSignature -LiteralPath $webView
        if ($sig.Status -ne 'Valid' -or !$sig.SignerCertificate -or
            $sig.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
            throw 'The bundled Microsoft WebView2 Offline Runtime is not validly signed.'
        }
        Write-Host 'Installing Microsoft WebView2 offline runtime...'
        $proc=Start-Process -FilePath $webView -ArgumentList '/silent','/install' -Wait -PassThru
        if ($proc.ExitCode -notin @(0,3010)) {
            throw ('WebView2 setup failed, exit code: '+$proc.ExitCode)
        }
        $version=Get-WebView2Installed
        if (!$version -and $proc.ExitCode -eq 3010) {
            throw 'WebView2 installed, but Windows must restart before completing setup.'
        }
        if (!$version) { throw 'WebView2 runtime could not be detected after installation.' }
    }
    Write-Host ('WebView2 runtime: '+$version)
}

# Refuse an existing different install. The operator must explicitly choose an
# empty versioned program directory instead of overwriting executable binaries.
$installed1=Join-Path $InstallRoot 'Madar-Desk.exe'
$installed2=Join-Path $InstallRoot 'Madar-Accounting.exe'
$installedBefore=[IO.Directory]::Exists($InstallRoot)
if ($installedBefore) {
    if (!(Test-Path $installed1) -or !(Test-Path $installed2)) {
        throw 'Install folder exists but is incomplete. It was left untouched.'
    }
    Verify-Sha $installed1 $manifest.apps.madarSha256
    Verify-Sha $installed2 $manifest.apps.accountingSha256
    Write-Host 'Identical applications already installed; no files overwritten.'
} else {
    Assert-NotRunning 'Madar-Desk.exe'
    Assert-NotRunning 'Madar-Accounting.exe'
    $parent=Split-Path -Parent $InstallRoot
    [void][IO.Directory]::CreateDirectory($parent)
    $staging=Join-Path $parent ('.madar-suite-stage-'+[guid]::NewGuid().ToString('N'))
    $published=$false
    try {
        [void][IO.Directory]::CreateDirectory($staging)
        [IO.File]::Copy($source1,(Join-Path $staging 'Madar-Desk.exe'),$false)
        [IO.File]::Copy($source2,(Join-Path $staging 'Madar-Accounting.exe'),$false)
        Verify-Sha (Join-Path $staging 'Madar-Desk.exe') $manifest.apps.madarSha256
        Verify-Sha (Join-Path $staging 'Madar-Accounting.exe') $manifest.apps.accountingSha256
        # Same-parent rename is atomic; never copy a partially completed EXE
        # directly onto the final name.
        [IO.Directory]::Move($staging,$InstallRoot)
        $published=$true
    } finally {
        if (!$published -and (Test-Path $staging)) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
    }
}

# Dedicated data on a per-user writable path. No task, database, old backup or
# existing APPDATA file is imported, deleted or replaced by installation.
$accountingData=Join-Path $DataRoot 'Accounting'
[void][IO.Directory]::CreateDirectory($accountingData)
$hasRecovery=$false
if ($manifest.PSObject.Properties.Name -contains 'appCapabilities') {
    if ($manifest.appCapabilities.PSObject.Properties.Name -contains 'accountingRecoveryUI') {
        $hasRecovery=($manifest.appCapabilities.accountingRecoveryUI -eq $true)
    }
}

if (!$NoShortcuts) {
    $shortcuts=@(
        @{filename='مدار - مدیریت کارها.lnk';target=$installed1;args='';icon=$installed1},
        @{filename='مدار - حسابداری مستقل.lnk';target=$installed2;
          args=('--data-dir "'+$accountingData+'"');icon=$installed2}
    )
    if ($hasRecovery) {
        $shortcuts += @{
            filename='مدار - بازیابی آفلاین حسابداری.lnk'
            target=$installed2
            args=('--restore-ui')
            icon=$installed2
        }
    }
    if ($TestShortcutRoot) {
        if ($env:MADAR_INSTALL_QA -ne '1') { throw 'Shortcut redirection is QA-only.' }
        $shortcutRoot=Assert-AbsoluteLocal $TestShortcutRoot
        $desktop=Join-Path $shortcutRoot 'Desktop'
        $menu=Join-Path $shortcutRoot 'StartMenu\Programs\Madar Suite'
        [void][IO.Directory]::CreateDirectory($desktop)
    } else {
        $desktop=[Environment]::GetFolderPath('DesktopDirectory')
        $menu=Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Madar Suite'
    }
    [void][IO.Directory]::CreateDirectory($menu)
    $shell=New-Object -ComObject WScript.Shell
    foreach($folder in @($desktop,$menu)){
        foreach($shortcut in $shortcuts) {
            $file=Join-Path $folder $shortcut.filename
            if ([IO.File]::Exists($file)) {
                # Do not overwrite shortcuts that belong to another installation.
                $existing=$shell.CreateShortcut($file)
                if ($existing.TargetPath -ine $shortcut.target) {
                    throw ('Different shortcut already exists; did not overwrite: '+$file)
                }
            }
            $link=$shell.CreateShortcut($file)
            $link.TargetPath=$shortcut.target
            $link.Arguments=$shortcut.args
            $link.WorkingDirectory=$InstallRoot
            $link.IconLocation=$shortcut.icon+',0'
            $link.Description='Madar Suite'
            $link.Save()
        }
    }
}
Write-Host ('INSTALL_SUCCESS '+$InstallRoot)
Write-Host ('ACCOUNTING_DATA '+$accountingData)
if (!$Silent) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show(
            'مدار و حسابداری مستقل نصب شدند. میانبر هر دو برنامه روی دسکتاپ قرار گرفت.',
            'نصب مدار', [Windows.Forms.MessageBoxButtons]::OK)
    } catch {}
}
