# Explicitly invoked, local-only customer issue report. Does not read application data.
# Requires an existing local output directory outside application/system data roots.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$')]
    [string]$AppVersion,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory,

    # Leave this unset to type the message without placing it on the command line.
    [string]$ErrorMessage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-AtOrWithin([string]$Candidate, [string]$Parent) {
    if ([string]::IsNullOrWhiteSpace($Parent)) { return $false }
    $a = [System.IO.Path]::GetFullPath($Candidate).TrimEnd('\')
    $b = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\')
    return ($a.Equals($b, [StringComparison]::OrdinalIgnoreCase) -or
            $a.StartsWith($b + '\', [StringComparison]::OrdinalIgnoreCase))
}

function Assert-SafeOutputDirectory([string]$Requested) {
    if ($Requested -notmatch '^[A-Za-z]:[\\/]') {
        throw 'OutputDirectory must be an explicit absolute local drive path.'
    }
    $full = [System.IO.Path]::GetFullPath($Requested)
    if (![System.IO.Directory]::Exists($full)) {
        throw 'OutputDirectory must already exist; no report was created.'
    }
    $root = [System.IO.Path]::GetPathRoot($full)
    if ($full.TrimEnd('\').Equals($root.TrimEnd('\'),
                                    [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A drive root cannot hold issue reports.'
    }
    foreach ($protected in @($env:APPDATA, $env:LOCALAPPDATA, $env:PROGRAMDATA,
                              $env:WINDIR, $env:ProgramFiles,
                              [Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))) {
        if ($protected -and (Test-AtOrWithin $full $protected)) {
            throw 'OutputDirectory is inside a protected data or system directory.'
        }
    }
    foreach ($synced in @($env:OneDrive, $env:OneDriveConsumer,
                           $env:OneDriveCommercial, $env:Dropbox)) {
        if ($synced -and (Test-AtOrWithin $full $synced)) {
            throw 'OutputDirectory is inside a known cloud-synced folder.'
        }
    }
    if ($full -match '(?i)[\\/](?:OneDrive(?: - [^\\/]+)?|Dropbox|Google Drive)[\\/]?') {
        throw 'OutputDirectory appears to be cloud-synced; choose a private local folder.'
    }
    # A junction could otherwise redirect a seemingly safe folder into APPDATA.
    $cursor = $full
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'OutputDirectory cannot contain symlinks or junctions.'
        }
        $parent = [System.IO.Path]::GetDirectoryName($cursor)
        if (!$parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $full
}

function Protect-UserMessage([string]$Message) {
    if ([string]::IsNullOrWhiteSpace($Message)) {
        throw 'A short error description is required.'
    }
    # Accept only a short, user-supplied summary. Never search or import logs.
    $lines = @([regex]::Split($Message, '\r\n|\r|\n') | Select-Object -First 8)
    $safeLines = foreach ($line in $lines) {
        $line = [regex]::Replace($line, '[\x00-\x1f\x7f]', ' ')
        if ($line.Length -gt 300) { $line = $line.Substring(0, 300) }

        # Discard a whole line if it looks like credentials, stack-trace paths,
        # or personal profile locations. Partial masking would be unreliable.
        if ($line -match '(?i)\b(?:authorization|password|passwd|passphrase|pwd|secret|credential|bearer|cookie|private[ _-]?key|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|session|otp|pin)\b' -or
            $line -match '(?i)\b(?:user(?:name)?|login|account[ _-]?name|customer[ _-]?name|[A-Za-z_]*(?:password|token|secret|apikey)[A-Za-z_]*)\s*[:=]' -or
            $line -match '(?i)(?:(?<![A-Za-z0-9])[A-Z]:[\\/]|\\\\|%appdata%|%userprofile%|/(?:users|home)/|~[\\/])') {
            '[REDACTED_SENSITIVE_LINE]'
            continue
        }

        $line = [regex]::Replace($line, '(?i)\b(?:https?|ftp)://[^\s]+', '[REDACTED_URL]')
        $line = [regex]::Replace($line, '(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b', '[REDACTED_EMAIL]')
        $line = [regex]::Replace($line, '(?<!\w)@[A-Za-z0-9_]{2,}', '[REDACTED_HANDLE]')
        $line = [regex]::Replace($line, '(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)', '[REDACTED_IP]')
        $line = [regex]::Replace($line, '(?i)\b(?:[0-9a-f]{0,4}:){2,}[0-9a-f]{0,4}\b', '[REDACTED_IP]')
        $line = [regex]::Replace($line, '(?<![\d\u06F0-\u06F9\u0660-\u0669])\+?[\d\u06F0-\u06F9\u0660-\u0669][\d\u06F0-\u06F9\u0660-\u0669 ()\.\-]{7,}[\d\u06F0-\u06F9\u0660-\u0669](?![\d\u06F0-\u06F9\u0660-\u0669])', '[REDACTED_NUMBER]')
        $line = [regex]::Replace($line, '(?<![A-Za-z0-9_])[A-Za-z0-9_+\-/=]{32,}(?![A-Za-z0-9_])', '[REDACTED_LONG_VALUE]')
        $line
    }
    $result = ($safeLines -join "`n").Trim()
    if (!$result) { throw 'A short error description is required.' }
    return $result
}

if (!$PSBoundParameters.ContainsKey('ErrorMessage')) {
    $ErrorMessage = Read-Host 'Describe the error briefly (do not paste logs or personal data)'
}

# Validate everything before opening any file for writing.
$safeMessage = Protect-UserMessage $ErrorMessage
$destination = Assert-SafeOutputDirectory $OutputDirectory
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This report tool supports Windows only.'
}

$report = [ordered]@{
    schema_version = 1
    created_utc = [DateTime]::UtcNow.ToString('o')
    app_version = $AppVersion
    os = [ordered]@{
        platform = [Environment]::OSVersion.Platform.ToString()
        version = [Environment]::OSVersion.Version.ToString()
        is_64_bit = [Environment]::Is64BitOperatingSystem
    }
    runtime = [ordered]@{
        powershell_version = $PSVersionTable.PSVersion.ToString()
        dotnet_version = [Environment]::Version.ToString()
        is_64_bit_process = [Environment]::Is64BitProcess
    }
    error_description = $safeMessage
}

$json = $report | ConvertTo-Json -Depth 5
$filename = 'madar-issue-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') +
            '-' + [Guid]::NewGuid().ToString('N') + '.json'
$outputPath = Join-Path $destination $filename
$tempPath = Join-Path $destination ('.' + $filename + '.tmp')
$stream = $null
try {
    $stream = New-Object System.IO.FileStream(
        $tempPath, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes($json + "`n")
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
    $stream.Dispose()
    $stream = $null
    # Same-folder rename publishes only a complete report, without overwrite.
    [System.IO.File]::Move($tempPath, $outputPath)
} finally {
    if ($stream) { $stream.Dispose() }
    if ([System.IO.File]::Exists($tempPath)) {
        [System.IO.File]::Delete($tempPath)
    }
}

# Only a local path is returned. No network, clipboard or implicit submission.
Write-Output $outputPath
