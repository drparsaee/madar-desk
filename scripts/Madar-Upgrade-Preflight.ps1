# Internal helper for the versioned Inno Setup updater. Never run automatically
# on app startup; only after a user explicitly starts an installer.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DataRoot,
    [Parameter(Mandatory=$true)][string]$BackupRoot,
    [Parameter(Mandatory=$true)][string]$TargetVersion
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($TargetVersion -cnotmatch '^\d+\.\d+\.\d+$') { throw 'Invalid upgrade version.' }

function Resolve-PathSafely([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch '^[A-Za-z]:[\\/]') {
        throw 'Expected explicit absolute Windows path.'
    }
    $full=[IO.Path]::GetFullPath($Value)
    # An input such as X:\ or X:\folder\.. must not become X: (a
    # drive-relative path), or turn a customer profile into an entire volume.
    if ($full.Equals([IO.Path]::GetPathRoot($full),[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Drive root is not an allowed Madar data or backup directory.'
    }
    return $full.TrimEnd('\')
}
function IsInside([string]$Path, [string]$Root) {
    return $Path.Equals($Root,[StringComparison]::OrdinalIgnoreCase) -or
        $Path.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase)
}
function AssertNoLinks([string]$Path) {
    $current=$Path
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if (Test-Path -LiteralPath $current) {
            $item=Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw ('Linked/junction path is not safe to back up: '+$current)
            }
        }
        $next=[IO.Path]::GetDirectoryName($current)
        if ($next -eq $current) {break}
        $current=$next
    }
}
$DataRoot=Resolve-PathSafely $DataRoot
$BackupRoot=Resolve-PathSafely $BackupRoot
if (IsInside $DataRoot $BackupRoot) {throw 'Backup path overlaps user data.'}
if (IsInside $BackupRoot $DataRoot) {throw 'Backup path overlaps user data.'}
AssertNoLinks $DataRoot
AssertNoLinks $BackupRoot

# The native desktop and LAN Host must not be writing while SQLite and WAL
# files are copied. Never terminate a running customer application.
$running=@(Get-Process -ErrorAction Stop | Where-Object {
    $_.ProcessName -like 'Madar-Desk*' -or $_.ProcessName -eq 'MadarHost'
})
if ($running.Count -gt 0) {throw 'Close all Madar windows and MadarHost before updating.'}
$service=Get-Service -Name 'MadarHost' -ErrorAction SilentlyContinue
if ($null -ne $service -and $service.Status -eq 'Running') {
    throw 'Stop the MadarHost service before updating.'
}

if (-not (Test-Path -LiteralPath $DataRoot -PathType Container)) {
    Write-Output 'FRESH_PROFILE: no prior user data to back up.'
    exit 0
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$files=@(Get-ChildItem -LiteralPath $DataRoot -File -Recurse -Force -ErrorAction Stop)
$items=@(Get-ChildItem -LiteralPath $DataRoot -Recurse -Force -ErrorAction Stop)
foreach($entry in $items) {
    if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw ('Cannot back up symlink/junction: '+$entry.FullName)
    }
}
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$stamp=[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fffffff')
$identity=[guid]::NewGuid().ToString('N')
$archive=Join-Path $BackupRoot ('Madar-Before-'+$TargetVersion+'-'+$stamp+'-'+$identity+'.zip')
# Never expose a damaged or unverified archive as a completed backup. The
# temporary file is on the same volume as its final destination.
$partial=Join-Path $BackupRoot ('.Madar-InProgress-'+$identity+'.partial')
try {
    [IO.Compression.ZipFile]::CreateFromDirectory($DataRoot,$partial,[IO.Compression.CompressionLevel]::Optimal,$false)

# Verify file count, byte sizes and contents. This is a stable offline
# snapshot, not merely an archive that opens successfully.
$zip=[IO.Compression.ZipFile]::OpenRead($partial)
try {
    $zipFiles=@($zip.Entries | Where-Object {$_.Name -ne ''})
    if ($zipFiles.Count -ne $files.Count) {throw 'Snapshot file count differs from data.'}
    # A dictionary makes matching O(n) for large user profiles while keeping
    # the previous case-sensitive Windows archive contract.
    $entryMap=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach ($entry in $zipFiles) {
        $key=$entry.FullName.Replace('\','/')
        if ($entryMap.ContainsKey($key)) {throw ('Duplicate snapshot entry: '+$key)}
        $entryMap.Add($key,$entry)
    }
    $sha=[Security.Cryptography.SHA256]::Create()
    try {
        foreach($file in $files) {
            $relative=$file.FullName.Substring($DataRoot.Length+1).Replace('\','/')
            if (-not $entryMap.ContainsKey($relative)) {
                throw ('Snapshot mismatch: '+$relative)
            }
            $match=$entryMap[$relative]
            if ($match.Length -ne $file.Length) {
                throw ('Snapshot mismatch: '+$relative)
            }
            $source=[IO.File]::OpenRead($file.FullName)
            try {$sourceHash=[BitConverter]::ToString($sha.ComputeHash($source))}
            finally {$source.Dispose()}
            $stream=$match.Open()
            try {$archiveHash=[BitConverter]::ToString($sha.ComputeHash($stream))}
            finally {$stream.Dispose()}
            if ($sourceHash -cne $archiveHash) {throw ('Snapshot checksum mismatch: '+$relative)}
        }
    } finally {$sha.Dispose()}
} finally {$zip.Dispose()}
    # This rename is atomic on the backup volume and is only reached after
    # every source file was checked against the archive.
    [IO.File]::Move($partial,$archive)
} finally {
    if (Test-Path -LiteralPath $partial) {Remove-Item -LiteralPath $partial -Force}
}
Write-Output ('BACKUP_VERIFIED: '+$archive)
