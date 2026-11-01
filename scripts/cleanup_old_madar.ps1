# Clean only the known old Madar Windows installs and historical build packages.
# Never touches APPDATA/MadarDesk, accounting-company data, or private backups.
[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$release=Join-Path $repo 'release'
$local=$env:LOCALAPPDATA
$current=Join-Path $local 'Programs\MadarDesk'
$backups=Join-Path $local 'MadarDesk-ReleaseBackups'
if (-not(Test-Path (Join-Path $current 'current-version.txt'))) {throw 'Current install missing'}
if (((Get-Content (Join-Path $current 'current-version.txt') -Raw).Trim()) -cne '1.0.2') {
    throw 'The currently installed version is not 1.0.2'
}
$exe=Join-Path $current 'versions\1.0.2\Madar-Desk.exe'
$expected='B33DA7B33EBD761BCC381DD22DE49FA0AD071EE11FE0AD133D9C77CAA1917405'
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ine $expected) {throw 'Current EXE hash mismatch'}
$required=@(
    @('Madar-Legacy-Accounting-Profiles-20261101.zip','C44DEF44CAFC14FC90A184A8B87F182CD30D103CE824C15B73B58BDF497C6FC8'),
    @('Madar-Legacy-Installed-Binaries-20261101.zip','15EE3A1D221985F12772B01D1E4D77CD1C2076C5DC0FB8C235AD33547CBFEEEC'),
    @('Madar-Before-1.0.2-20261101-144112-9397613.zip','42F177D74736AF15B5F77736A6CFFA94CF174B200B2C03D55DA734AD3A1E9778')
)
foreach($pair in $required) {
    $file=Join-Path $backups $pair[0]
    if (!(Test-Path -LiteralPath $file) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $pair[1]) {
        throw ('Mandatory recovery archive missing or changed: '+$pair[0])
    }
}
$running=@(Get-Process -ErrorAction Stop | Where-Object {$_.ProcessName -like 'Madar*'})
if ($running.Count -gt 0) {throw 'Close all Madar processes before cleanup'}
$base=Join-Path $local 'Programs'
$legacy=@(Get-ChildItem -LiteralPath $base -Directory | Where-Object {
    $_.Name -like 'Madar Accounting *' -or $_.Name -eq 'Madar Suite R5'
})
if ($legacy.Count -ne 15) {throw ('Unexpected legacy installed directory count: '+$legacy.Count)}
foreach($folder in $legacy) {
    if (($folder.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'Linked legacy directory'}
    $items=@(Get-ChildItem -LiteralPath $folder.FullName -Recurse -Force)
    foreach($item in $items) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'Linked legacy content'}
        if (!$item.PSIsContainer -and $item.Extension.ToLowerInvariant() -notin @('.exe','.ps1','.cmd')) {
            throw ('Potential user data inside an installation: '+$folder.Name)
        }
    }
}
$oldBinary=Join-Path $current 'versions\1.0.1'
if (-not(Test-Path -LiteralPath $oldBinary -PathType Container)) {throw 'Expected old 1.0.1 folder missing'}
$oldContent=@(Get-ChildItem -LiteralPath $oldBinary -Recurse -File)
if ($oldContent.Count -ne 1 -or $oldContent[0].Name -ne 'Madar-Desk.exe') {throw 'Unexpected old installation content'}
$keep=@('Madar-Setup-v1.0.2-Update-20261101-Fix1.exe','Madar-Desk-v1.0.2-Update-20261101.exe')
$obsolete=@(Get-ChildItem -LiteralPath $release -File | Where-Object {
    $_.Name -match '^(Madar|madar)' -and $_.Extension -in @('.exe','.zip') -and $_.Name -notin $keep
})
if ($obsolete.Count -lt 120 -or $obsolete.Count -gt 140) {
    throw ('Unexpected historical release count: '+$obsolete.Count)
}
$checksums=@(Get-ChildItem -LiteralPath $release -File | Where-Object {
    $_.Name -match '^(Madar|madar)' -and $_.Name -like '*.sha256.txt' -and
    $_.Name -ne 'Madar-Setup-v1.0.2-Update-20261101-Fix1.exe.sha256.txt'
})
$bytes=($obsolete|Measure-Object -Property Length -Sum).Sum
Write-Output ('VERIFIED_CLEANUP_PLAN legacy_installations='+$legacy.Count+' release_packages='+$obsolete.Count+' release_bytes='+$bytes+' checksum_files='+$checksums.Count)
if (!$Apply) {Write-Output 'DRY_RUN_ONLY';exit 0}
foreach($entry in $obsolete) {Remove-Item -LiteralPath $entry.FullName -Force -ErrorAction Stop}
foreach($entry in $checksums) {Remove-Item -LiteralPath $entry.FullName -Force -ErrorAction Stop}
foreach($folder in $legacy) {Remove-Item -LiteralPath $folder.FullName -Recurse -Force -ErrorAction Stop}
Remove-Item -LiteralPath $oldBinary -Recurse -Force -ErrorAction Stop
$previous=Join-Path $current 'previous-version.txt'
if (Test-Path -LiteralPath $previous) {
    if (((Get-Content -LiteralPath $previous -Raw).Trim()) -eq '1.0.1') {
        Remove-Item -LiteralPath $previous -Force
    }
}
$receipt=[ordered]@{
    dateUtc=[DateTime]::UtcNow.ToString('o')
    retainedVersion='1.0.2'
    deletedInstalledOldVersion='1.0.1'
    deletedLegacyInstallFolders=$legacy.Count
    deletedOldReleasePackages=$obsolete.Count
    deletedOldPackageBytes=$bytes
    deletedOldChecksumFiles=$checksums.Count
    backupsPreserved=@($required|ForEach-Object{$_[0]})
}
$destination=Join-Path $backups ('Madar-Cleanup-Receipt-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')+'.json')
$receipt|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $destination -Encoding UTF8
Write-Output ('CLEANUP_PASS_RECEIPT='+$destination)
