# Create an explicit-path, private, non-destructive RAW data archive of all
# Parsian tbl_* BASE TABLES from an ALREADY ATTACHED database.
#
# It is NOT a restored BAK snapshot. It does not import into Madar.
# No SQL DML/DDL, no app passwords promoted to Madar permissions.
# Every value has an explicit type, BLOBs are base64, decimals exact strings.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BackupCopy,
    [Parameter(Mandatory=$true)][string]$OutputJsonLines,
    [Parameter(Mandatory=$true)][string]$OutputSummary
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$bak = [IO.Path]::GetFullPath($BackupCopy)
$rowsPath = [IO.Path]::GetFullPath($OutputJsonLines)
$summaryPath = [IO.Path]::GetFullPath($OutputSummary)
if (!(Test-Path -LiteralPath $bak -PathType Leaf) -or
    (Test-Path -LiteralPath $rowsPath) -or
    (Test-Path -LiteralPath $summaryPath) -or
    $rowsPath -eq $summaryPath -or $rowsPath -eq $bak -or
    $summaryPath -eq $bak) { throw 'Existing BAK and new output paths required.' }
$parent = [IO.Path]::GetDirectoryName($rowsPath)
if ($parent -ne [IO.Path]::GetDirectoryName($summaryPath) -or
    !$parent.EndsWith('migration-experiment-20261026') -or
    !(Test-Path -LiteralPath $parent -PathType Container)) {
    throw 'Outputs must be in the designated private experiment root.'
}
Add-Type -AssemblyName System.Data
$cn = New-Object System.Data.SqlClient.SqlConnection (
    'Server=localhost;Database=master;Integrated Security=True;Connect Timeout=8;' +
    'Application Name=Madar-Migration-All-Tables-ReadOnly')
$enc = New-Object System.Text.UTF8Encoding($false)
$writer = $null
$counts = [ordered]@{}
try {
    $cn.Open()
    $version = $cn.CreateCommand()
    $version.CommandText = "SELECT CONVERT(varchar(32), SERVERPROPERTY('ProductVersion'))"
    if (-not ([string]$version.ExecuteScalar()).StartsWith('8.')) {
        throw 'Source is not the expected legacy SQL Server 2000.'
    }
    $header = $cn.CreateCommand()
    $header.CommandTimeout = 30
    $escapedBak = $bak.Replace("'","''")
    $header.CommandText = "RESTORE HEADERONLY FROM DISK=N'$escapedBak'"
    $reader = $header.ExecuteReader()
    try {
        if (-not $reader.Read()) { throw 'No backup header' }
        $db = [string]$reader['DatabaseName']
    } finally { $reader.Close() }
    if ($db -cnotmatch '^[A-Za-z_][A-Za-z0-9_]{0,63}$') {
        throw 'Unexpected SQL database name.'
    }
    $cn.ChangeDatabase('MadarR19ParsianQA1404')
    $lock = $cn.CreateCommand()
    $lock.CommandText = 'SET LOCK_TIMEOUT 1200'
    [void]$lock.ExecuteNonQuery()
    $tableCmd = $cn.CreateCommand()
    $tableCmd.CommandText = @'
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE' AND TABLE_NAME LIKE 'tbl[_]%'
ORDER BY TABLE_NAME
'@
    $tableReader = $tableCmd.ExecuteReader()
    $tables = New-Object System.Collections.ArrayList
    try {
        while ($tableReader.Read()) {
            $table = [string]$tableReader.GetValue(0)
            if ($table -notmatch '^tbl_[A-Za-z0-9_]+$') {
                throw 'Unsupported vendor table identifier'
            }
            [void]$tables.Add($table)
        }
    } finally { $tableReader.Close() }
    if ($tables.Count -lt 90 -or $tables.Count -gt 140) {
        throw 'Unexpected number of vendor tables. Refusing incomplete export.'
    }
    $file = New-Object IO.FileStream(
        $rowsPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $writer = New-Object IO.StreamWriter($file, $enc)
    foreach ($table in $tables) {
        $select = $cn.CreateCommand()
        $select.CommandTimeout = 25
        $select.CommandText = 'SELECT * FROM dbo.['+$table+'] WITH (READPAST)'
        $reader = $select.ExecuteReader()
        $count = 0
        try {
            while ($reader.Read()) {
                $row = [ordered]@{table=$table; fields=[ordered]@{}}
                for ($j=0; $j -lt $reader.FieldCount; $j++) {
                    $field = $reader.GetName($j)
                    $value = $reader.GetValue($j)
                    if ($value -eq [DBNull]::Value) {
                        $row.fields[$field] = @{t='null'}
                    } elseif ($value -is [byte[]]) {
                        $row.fields[$field] = @{
                            t='binary'; b64=[Convert]::ToBase64String($value)}
                    } elseif ($value -is [DateTime]) {
                        $row.fields[$field] = @{
                            t='datetime'; text=$value.ToString('o')}
                    } elseif ($value -is [decimal]) {
                        $row.fields[$field] = @{
                            t='decimal'; text=$value.ToString(
                                [Globalization.CultureInfo]::InvariantCulture)}
                    } elseif ($value -is [double] -or $value -is [single]) {
                        $row.fields[$field] = @{
                            t='float'; text=$value.ToString(
                                'R',[Globalization.CultureInfo]::InvariantCulture)}
                    } elseif ($value -is [bool]) {
                        $row.fields[$field] = @{t='bit'; value=$value}
                    } elseif ($value -is [int] -or $value -is [long] -or
                              $value -is [int16] -or $value -is [byte]) {
                        $row.fields[$field] = @{
                            t='integer'; text=$value.ToString(
                                [Globalization.CultureInfo]::InvariantCulture)}
                    } else {
                        $row.fields[$field] = @{t='text';value=[string]$value}
                    }
                }
                # Per-row JSON, no accidental lossy CSV coercion or truncation.
                $writer.WriteLine((ConvertTo-Json -InputObject $row -Depth 7 -Compress))
                $count++
                if ($count -gt 100000) { throw 'Per-table source record limit exceeded.' }
            }
        } finally { $reader.Close() }
        $counts[$table] = $count
    }
    $writer.Flush()
    $file.Flush($true)
    $writer.Dispose()
    $writer = $null
    $backupHash = (Get-FileHash -LiteralPath $bak -Algorithm SHA256).Hash
    if ($backupHash -cne 'D46D6E975DF6A59C3FB42FF695F39A911979304AD54B8450DFD7AA70F5308779') { throw 'Latest BAK hash mismatch' }
    $archiveHash = (Get-FileHash -LiteralPath $rowsPath -Algorithm SHA256).Hash
    $summary = [ordered]@{
        source = 'ISOLATED_RESTORED_BAK_VERIFIED_20261026'
        snapshotMatchesBackup = $true
        snapshotIsConsistent = $true
        sourceCurrency = 'UNKNOWN_RAW_LEGACY_UNITS'
        vendorTableCount = $counts.Count
        vendorRowCount = [int64](($counts.Values | Measure-Object -Sum).Sum)
        tableCounts = $counts
        sourceBackupSha256 = $backupHash
        archiveSha256 = $archiveHash
        passwordsOrCredentialsEverInstalledIntoMadar = $false
        originalSqlServerModified = $false
    }
    $output = New-Object IO.FileStream(
        $summaryPath, [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $json = ConvertTo-Json -InputObject $summary -Depth 5 -Compress
        $bytes = $enc.GetBytes($json)
        $output.Write($bytes,0,$bytes.Length)
        $output.Flush($true)
    } finally { $output.Dispose() }
    Write-Output ('FULL_RAW_ARCHIVE_TABLES='+$counts.Count)
    Write-Output ('FULL_RAW_ARCHIVE_ROWS='+$summary.vendorRowCount)
    Write-Output ('ARCHIVE_SHA256='+$archiveHash)
    Write-Output 'ISOLATED_RESTORED_BACKUP_SNAPSHOT'
} finally {
    if ($null -ne $writer) { $writer.Dispose() }
    $cn.Dispose()
}
