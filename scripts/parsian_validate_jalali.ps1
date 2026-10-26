# Builds a date-only PersianCalendar proof from an existing private SQL export.
# No source SQL access. No mutation of vendor or Madar data.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SourceExportJson,
    [Parameter(Mandatory=$true)][string]$OutputJson
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath($SourceExportJson)
$target = [IO.Path]::GetFullPath($OutputJson)
if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or
    (Test-Path -LiteralPath $target) -or $source -eq $target) {
    throw 'Expected an existing private source export and a new output filename.'
}
$raw = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
if ($raw.sourceType -notin @('ATTACHED_LIVE_SQL_READ_ONLY_NOT_BAK_SNAPSHOT','RESTORED_BAK_ISOLATED_VERIFIED_20261026')) {
    throw 'Unrecognized source format'
}
$seen = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($row in @($raw.tables.tbl_Document)) {
    [void]$seen.Add([string]$row.SanadDate)
}
foreach ($row in @($raw.tables.tbl_Factor)) {
    [void]$seen.Add([string]$row.Factor_Date)
}
$persian = New-Object System.Globalization.PersianCalendar
$mapping = [ordered]@{}
foreach ($value in ($seen | Sort-Object)) {
    if ($value -cnotmatch '^1[234][0-9][0-9]/(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])$') {
        throw 'Invalid Persian date spelling in source'
    }
    $parts = $value.Split('/')
    $dt = $persian.ToDateTime([int]$parts[0],[int]$parts[1],
                             [int]$parts[2],0,0,0,0)
    # Enforce round-trip against the .NET authoritative calendar.
    $roundTrip = $persian.GetYear($dt).ToString('0000') + '/' +
                 $persian.GetMonth($dt).ToString('00') + '/' +
                 $persian.GetDayOfMonth($dt).ToString('00')
    if ($roundTrip -cne $value) {
        throw 'Persian calendar round-trip mismatch'
    }
    $mapping[$value] = $dt.ToString('yyyy-MM-dd',
                                    [System.Globalization.CultureInfo]::InvariantCulture)
}
$result = [ordered]@{
    sourceClass = [string]$raw.sourceType
    calendar = 'System.Globalization.PersianCalendar'
    schemaVersion = 1
    dates = $mapping
}
$json = ConvertTo-Json -InputObject $result -Depth 5 -Compress
$bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($json)
$file = New-Object IO.FileStream($target,[IO.FileMode]::CreateNew,
                                 [IO.FileAccess]::Write,[IO.FileShare]::None)
try {
    $file.Write($bytes,0,$bytes.Length)
    $file.Flush($true)
} finally { $file.Dispose() }
Write-Output ('JALALI_DATES_VALIDATED='+$mapping.Count)
Write-Output 'SOURCE_DATA_NOT_EDITED'
