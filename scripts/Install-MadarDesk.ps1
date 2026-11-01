# Portable Madar Desk EXE installer/updater. No MSI, registry, network or data migration.
# Deliberately changes only Madar-Desk.exe and uniquely named installer-owned files
# inside the explicit destination folder. Invoke manually, never from app startup.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$SourceExe,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$InstallDir,
    [ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSha256,
    # Explicit fault-injection hook for synthetic rollback tests, never for installation.
    [switch]$TestFailAfterBackup,
    [switch]$TestFailAfterRename
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-PlainPath([string]$PathValue) {
    # Relative destinations and UNC/device paths make the install boundary
    # ambiguous. Require ordinary absolute drive-letter paths.
    if ($PathValue -notmatch '^[A-Za-z]:[\\/]') {
        throw 'Only explicit local absolute drive paths are accepted.'
    }
    $full = [System.IO.Path]::GetFullPath($PathValue)
    if ($full.StartsWith('\\') -or $full.StartsWith('\\?\')) {
        throw 'UNC and device paths are not supported.'
    }
    return $full
}

function Test-AtOrWithin([string]$Candidate, [string]$Parent) {
    if ([string]::IsNullOrWhiteSpace($Parent)) { return $false }
    $a = $Candidate.TrimEnd('\')
    $b = $Parent.TrimEnd('\')
    return ($a.Equals($b, [StringComparison]::OrdinalIgnoreCase) -or
            $a.StartsWith($b + '\', [StringComparison]::OrdinalIgnoreCase))
}

function Assert-NoReparseAncestor([string]$FullPath) {
    $current = $FullPath
    while ($current) {
        if ([System.IO.File]::Exists($current) -or [System.IO.Directory]::Exists($current)) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw ('Reparse points and junctions are not allowed: ' + $current)
            }
        }
        $parent = [System.IO.Path]::GetDirectoryName($current)
        if (!$parent -or $parent -eq $current) { break }
        $current = $parent
    }
}

function Assert-PeExe([string]$FilePath) {
    $stream = $null
    $reader = $null
    try {
        $stream = [System.IO.File]::Open(
            $FilePath, [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
        if ($stream.Length -lt 512) { throw 'Not a valid PE: file is too small.' }
        $reader = New-Object System.IO.BinaryReader($stream)
        if ($reader.ReadUInt16() -ne 0x5a4d) { throw 'Not a valid PE: missing MZ header.' }
        [void]$stream.Seek(0x3c, [System.IO.SeekOrigin]::Begin)
        $peOffset = $reader.ReadInt32()
        if ($peOffset -lt 0x40 -or [long]$peOffset + 24 -gt $stream.Length) {
            throw 'Not a valid PE: header offset is invalid.'
        }
        [void]$stream.Seek($peOffset, [System.IO.SeekOrigin]::Begin)
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw 'Not a valid PE: missing PE signature.'
        }
        $machine = $reader.ReadUInt16()
        $sections = $reader.ReadUInt16()
        [void]$stream.Seek(12, [System.IO.SeekOrigin]::Current)
        $optionalSize = $reader.ReadUInt16()
        [void]$reader.ReadUInt16()  # COFF characteristics
        if ($machine -notin @(0x14c, 0x8664, 0xaa64) -or
            $sections -lt 1 -or $sections -gt 96 -or
            $optionalSize -lt 96 -or
            [long]$peOffset + 24 + $optionalSize + 40 * $sections -gt $stream.Length) {
            throw 'Not a valid PE: truncated or unsupported COFF headers.'
        }
        $magic = $reader.ReadUInt16()
        if ($magic -notin @(0x10b, 0x20b) -or
            ($magic -eq 0x20b -and $optionalSize -lt 112)) {
            throw 'Not a valid PE: optional header magic is invalid.'
        }
    } finally {
        if ($reader) { $reader.Dispose() }
        elseif ($stream) { $stream.Dispose() }
    }
}

function Assert-TargetNotRunning([string]$TargetFile) {
    # Check named processes first. If their path cannot be inspected, refuse:
    # optimistic renaming of a running Windows image is not an acceptable update.
    foreach ($process in (Get-Process -Name 'Madar-Desk' -ErrorAction SilentlyContinue)) {
        try {
            $runningPath = $process.MainModule.FileName
        } catch {
            throw 'A Madar-Desk process is running but its path cannot be verified. Close it first.'
        }
        if ([string]::Equals($runningPath, $TargetFile,
                             [StringComparison]::OrdinalIgnoreCase)) {
            throw 'The installed Madar-Desk.exe is running. Close it before updating.'
        }
    }
    if ([System.IO.File]::Exists($TargetFile)) {
        $exclusive = $null
        try {
            $exclusive = [System.IO.File]::Open(
                $TargetFile, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        } catch {
            throw 'The installed EXE is in use or not writable; update was refused.'
        } finally {
            if ($exclusive) { $exclusive.Dispose() }
        }
    }
}

$source = Assert-PlainPath $SourceExe
$destination = Assert-PlainPath $InstallDir
$root = [System.IO.Path]::GetPathRoot($destination)
if ($destination.TrimEnd('\').Equals($root.TrimEnd('\'),
                                         [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Cannot install in a drive root.'
}

foreach ($sensitive in @($env:APPDATA, $env:LOCALAPPDATA, $env:PROGRAMDATA,
                         $env:WINDIR, $env:ProgramFiles,
                         [Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))) {
    if ($sensitive -and (Test-AtOrWithin $destination $sensitive)) {
        throw 'InstallDir is inside a protected application/system data directory.'
    }
}

if (![System.IO.File]::Exists($source)) { throw 'SourceExe does not exist.' }
if ([System.IO.Path]::GetExtension($source) -ine '.exe') {
    throw 'SourceExe must have the .exe extension.'
}
if (Test-AtOrWithin $source $destination) {
    throw 'SourceExe must be outside InstallDir to preserve release artifacts.'
}

Assert-NoReparseAncestor $source
Assert-NoReparseAncestor $destination
Assert-PeExe $source
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedSha256 -and $sourceHash -ne $ExpectedSha256.ToLowerInvariant()) {
    throw 'SourceExe SHA-256 does not match ExpectedSha256; no files were changed.'
}

$target = Join-Path $destination 'Madar-Desk.exe'
$lockPath = Join-Path $destination '.madar-portable-install.lock'
$lockStream = $null
$staged = $null
$backup = $null
$movedExisting = $false
$installedNew = $false
$committed = $false
try {
    if (![System.IO.Directory]::Exists($destination)) {
        [void][System.IO.Directory]::CreateDirectory($destination)
    }
    Assert-NoReparseAncestor $destination
    # CreateNew + FileShare.None prevents two installers from racing. An
    # abandoned lock causes safe refusal until manually inspected.
    try {
        $lockStream = [System.IO.File]::Open(
            $lockPath, [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch {
        throw 'InstallDir is locked or not writable; no update attempted.'
    }

    Assert-TargetNotRunning $target
    if ([System.IO.File]::Exists($target)) {
        Assert-NoReparseAncestor $target
        Assert-PeExe $target   # Never overwrite an unrelated/non-PE named file.
        $previousHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($previousHash -eq $sourceHash -and
            !$TestFailAfterBackup -and !$TestFailAfterRename) {
            # Do not rely on PowerShell's width-dependent table renderer for
            # machine verification: the Sha256 property can print as two
            # characters on narrow hosts despite a valid 64-byte digest.
            Write-Output ('INSTALL_VERIFIED_SHA256: ' + $previousHash)
            [pscustomobject]@{
                Installed = $target
                Sha256 = $previousHash
                Backup = $null
                Updated = $false
                Unchanged = $true
            }
            return
        }
    } elseif ([System.IO.Directory]::Exists($target)) {
        throw 'Install target is a directory, not an EXE.'
    }

    $nonce = [Guid]::NewGuid().ToString('N')
    $staged = Join-Path $destination ('.Madar-Desk.stage.' + $nonce + '.exe')
    [System.IO.File]::Copy($source, $staged, $false)
    Assert-PeExe $staged
    $stagedHash = (Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($stagedHash -ne $sourceHash) {
        throw 'Staged EXE hash differs from preflight source; update aborted.'
    }

    if ([System.IO.File]::Exists($target)) {
        # The app may have started while we were copying the staging file.
        Assert-TargetNotRunning $target
        $backupName = 'Madar-Desk.backup.' +
                      [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') +
                      '.' + [Guid]::NewGuid().ToString('N') + '.exe'
        $backup = Join-Path $destination $backupName
        [System.IO.File]::Move($target, $backup)
        $movedExisting = $true
    }

    if ($TestFailAfterBackup) {
        throw 'Injected test failure after backup (no installation performed).'
    }
    # Same-directory NTFS rename of the completed staged file is atomic. There
    # is no direct in-place overwrite of the target executable.
    [System.IO.File]::Move($staged, $target)
    $installedNew = $true
    $staged = $null
    if ($TestFailAfterRename) {
        throw 'Injected test failure after new target rename (rollback required).'
    }
    $installedHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($installedHash -ne $sourceHash) {
        throw 'Installed target checksum differs from validated stage.'
    }
    $committed = $true
    Write-Output ('INSTALL_VERIFIED_SHA256: ' + $installedHash)
    [pscustomobject]@{
        Installed = $target
        Sha256 = $installedHash
        Backup = $backup
        Updated = $movedExisting
    }
} catch {
    $originalError = $_
    if (!$committed) {
        if ($movedExisting -and $backup -and [System.IO.File]::Exists($backup)) {
            # A failed post-rename verification must not destroy the new file.
            # Retain it under a unique failure name, then restore the old EXE.
            if ([System.IO.File]::Exists($target)) {
                $failed = Join-Path $destination (
                    'Madar-Desk.failed.' + [Guid]::NewGuid().ToString('N') + '.exe')
                [System.IO.File]::Move($target, $failed)
            }
            try {
                [System.IO.File]::Move($backup, $target)
            } catch {
                throw ('ROLLBACK FAILED: original EXE remains at ' + $backup +
                       '; restore manually. Initial error: ' + $originalError)
            }
        } elseif ($installedNew -and [System.IO.File]::Exists($target)) {
            # A first-time install has no old EXE to restore. Quarantine the
            # failed new EXE instead of leaving an unverified live target.
            $failed = Join-Path $destination (
                'Madar-Desk.failed.' + [Guid]::NewGuid().ToString('N') + '.exe')
            [System.IO.File]::Move($target, $failed)
        }
    }
    throw $originalError
} finally {
    if ($staged -and [System.IO.File]::Exists($staged)) {
        [System.IO.File]::Delete($staged)
    }
    if ($lockStream) {
        $lockStream.Dispose()
        # This is the exact lock created by this invocation, never a preexisting lock.
        [System.IO.File]::Delete($lockPath)
    }
}
