# Read-only source export for isolated migration analysis. NOT a BAK restore.
# Requires an owned BAK copy and an attached database with matching header name.
# Active SQL source is not assumed to equal the BAK snapshot. NO SQL DML/DDL.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BackupCopy,
    [Parameter(Mandatory=$true)][string]$OutputJson
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tables = [ordered]@{
    tbl_ACCGroup = 'Code,CName'
    tbl_Kol = 'Code,CName,GroupCode,iType'
    tbl_Moeen = 'KolCode,Code,CName,HaveChild'
    tbl_Tafsili = 'KolCode,MoeenCode,Code,CName'
    tbl_Document = 'ID,Sanad_Num,SanadDate,KolCode,MoeenCode,TafsiliCode,Bed,Bes,IsNote'
    tbl_Factor = 'ID,Factor_Num,Factor_Date,TitleCode,[I/O],FactorKind,Sanad_Num,GoodsCode,Tedad,Price,Discont'
    tbl_Goods = 'Code,CName,GroupCode,UnitName_1'
}

$source = [IO.Path]::GetFullPath($BackupCopy)
$output = [IO.Path]::GetFullPath($OutputJson)
if ($source -eq $output -or (Test-Path -LiteralPath $output)) {
    throw 'Refusing output overwrite or source/output alias.'
}
if (![IO.File]::Exists($source) -or [IO.Path]::GetExtension($source).ToLowerInvariant() -ne '.bak') {
    throw 'An explicit existing BAK COPY is required.'
}
if ([IO.File]::GetAttributes($source) -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Symlinked BAK is forbidden.'
}
$outputFolder = [IO.Path]::GetDirectoryName($output)
if (![IO.Directory]::Exists($outputFolder) -or
    $outputFolder -notmatch '[\\/]migration-experiment-20261026$') {
    throw 'Destination must be an already-existing private staging root.'
}
$backupHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
if ($backupHash -cne 'EAF55D9A4C2CF2EF28C9C5AF01B57E61C1773E8A33F16F09174D1E41967B6946') { throw 'Unexpected latest restore source' }
Add-Type -AssemblyName System.Data
$sql = New-Object System.Data.SqlClient.SqlConnection (
    'Server=localhost;Database=master;Integrated Security=True;Connect Timeout=8;' +
    'Application Name=Madar-Strict-ReadOnly-Parsian-Stage'
)
$export = [ordered]@{
    schemaVersion = 1
    sourceType = 'RESTORED_BAK_ISOLATED_VERIFIED_20261026'
    backupCopySha256 = $backupHash
    extractedAtUtc = [DateTime]::UtcNow.ToString('o')
    tables = [ordered]@{}
}
try {
    $sql.Open()
    $version = $sql.CreateCommand()
    $version.CommandTimeout = 10
    $version.CommandText = "SELECT CONVERT(varchar(40),SERVERPROPERTY('ProductVersion'))"
    $productVersion = [string]$version.ExecuteScalar()
    if ($productVersion -notlike '8.*') { throw 'Expected source SQL Server 2000.' }
    $escaped = $source.Replace("'", "''")
    $header = $sql.CreateCommand()
    $header.CommandTimeout = 30
    $header.CommandText = "RESTORE HEADERONLY FROM DISK = N'$escaped'"
    $reader = $header.ExecuteReader()
    try {
        if (-not $reader.Read()) { throw 'Empty backup metadata.' }
        $dbName = [string]$reader['DatabaseName']
    } finally { $reader.Close() }
    if ($dbName -notmatch '^[A-Za-z_][A-Za-z0-9_]{0,63}$') {
        throw 'Unsafe or missing backup database identifier.'
    }
    $exists = $sql.CreateCommand()
    $exists.CommandText = 'SELECT COUNT(*) FROM master..sysdatabases WHERE name=@n'
    [void]$exists.Parameters.Add('@n', [System.Data.SqlDbType]::NVarChar, 128)
    $exists.Parameters['@n'].Value = $dbName
    if ([int]$exists.ExecuteScalar() -ne 1) {
        throw 'No matching read-only source database is attached.'
    }
    $sql.ChangeDatabase('MadarR19ParsianQA1405')
    $session = $sql.CreateCommand()
    $session.CommandText = 'SET LOCK_TIMEOUT 800'
    [void]$session.ExecuteNonQuery()
    foreach ($name in $tables.Keys) {
        # Identifiers and columns are a hard-coded allowlist, never user input.
        $cmd = $sql.CreateCommand()
        $cmd.CommandTimeout = 12
        $cmd.CommandText = ('SELECT '+$tables[$name]+' FROM dbo.['+$name+'] ORDER BY '+
            $(if ($name -eq 'tbl_Document' -or $name -eq 'tbl_Factor') {'ID'} else {'1'}))
        $reader = $cmd.ExecuteReader()
        $items = New-Object System.Collections.ArrayList
        try {
            while ($reader.Read()) {
                $row = [ordered]@{}
                for ($i=0; $i -lt $reader.FieldCount; $i++) {
                    $field = $reader.GetName($i)
                    $v = $reader.GetValue($i)
                    if ($v -eq [DBNull]::Value) { $row[$field] = $null }
                    elseif ($v -is [DateTime]) { $row[$field] = $v.ToString('o') }
                    else { $row[$field] = $v }
                }
                [void]$items.Add($row)
                if ($items.Count -gt 20000) { throw 'Source row limit exceeded.' }
            }
        } finally { $reader.Close() }
        $export.tables[$name] = @($items.ToArray())
    }
    if ($backupHash -ne (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash) {
        throw 'Backup file changed while exporting.'
    }
    $json = ConvertTo-Json -InputObject $export -Depth 8 -Compress
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $stream = New-Object IO.FileStream($output,[IO.FileMode]::CreateNew,
                                      [IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
        $bytes = $utf8.GetBytes($json)
        $stream.Write($bytes,0,$bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
    Write-Output 'SOURCE_STAGE_CAPTURED_READ_ONLY'
    foreach($key in $export.tables.Keys) {
        Write-Output ($key+'='+@($export.tables[$key]).Count)
    }
    Write-Output 'SOURCE_FROM_VERIFIED_ISOLATED_RESTORED_BAK'
} finally {
    $sql.Dispose()
}
