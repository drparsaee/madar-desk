# Internal Inno Setup helper. Switch only the version pointer, never user data.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$ExpectedSHA256
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($InstallRoot -notmatch '^[A-Za-z]:[\\/]' -or $Version -cnotmatch '^\d+\.\d+\.\d+$' -or
    $ExpectedSHA256 -cnotmatch '^[0-9A-Fa-f]{64}$') {
    throw 'Invalid activation arguments.'
}
$resolvedRoot=[IO.Path]::GetFullPath($InstallRoot)
# A drive root (including paths normalizing to it) is never an installation
# directory. TrimEnd alone would turn X:\ into the drive-relative X:.
if ($resolvedRoot.Equals([IO.Path]::GetPathRoot($resolvedRoot),[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Drive root is not an allowed Madar installation directory.'
}
$InstallRoot=$resolvedRoot.TrimEnd('\')
$exe=Join-Path $InstallRoot ('versions\'+$Version+'\Madar-Desk.exe')
$pointer=Join-Path $InstallRoot 'current-version.txt'
$previousPointer=Join-Path $InstallRoot 'previous-version.txt'
function AssertNoReparsePoints([string]$Path) {
    # Elevated activation must never follow a junction/symlink outside the
    # explicitly selected installation folder, including linked pointer files.
    $current=$Path
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        $item=Get-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue
        if ($null -ne $item -and
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw ('Linked or junction activation path is not allowed: '+$current)
        }
        $parent=[IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) {break}
        $current=$parent
    }
}
AssertNoReparsePoints $exe
AssertNoReparsePoints $pointer
AssertNoReparsePoints $previousPointer
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {throw 'Target program is missing.'}
$actual=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
if ($actual -ine $ExpectedSHA256) {throw 'Target program integrity verification failed.'}
if (Test-Path -LiteralPath $pointer) {
    $previous=(Get-Content -LiteralPath $pointer -Raw).Trim()
    if ($previous -cnotmatch '^\d+\.\d+\.\d+$') {throw 'Existing version pointer is malformed.'}
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot ('versions\'+$previous+'\Madar-Desk.exe')) -PathType Leaf)) {
        throw 'Current installed version missing; refusing unsafe switch.'
    }
    if ($previous -ceq $Version) {
        # Same-version repair/reinstall must not overwrite the last genuinely
        # older version stored in previous-version.txt.
        Write-Output ('VERSION_ALREADY_ACTIVE: '+$Version)
        exit 0
    }
}
$tmp=Join-Path $InstallRoot ('current-version-'+[guid]::NewGuid().ToString('N')+'.tmp')
try {
    [IO.File]::WriteAllText($tmp,$Version+[Environment]::NewLine,(New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $pointer) {
        [IO.File]::Replace($tmp,$pointer,$previousPointer)
    } else {
        Move-Item -LiteralPath $tmp -Destination $pointer -ErrorAction Stop
    }
} finally {
    if(Test-Path -LiteralPath $tmp){Remove-Item -LiteralPath $tmp -Force}
}
Write-Output ('VERSION_ACTIVATED: '+$Version)
