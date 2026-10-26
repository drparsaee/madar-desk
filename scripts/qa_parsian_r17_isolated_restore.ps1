# Restore ONLY a uniquely named temporary QA database, never db_1405.
# Designed for the user's explicit Parsian migration trial on local SQL 2000.
# Refuses existing SQL database, any existing destination MDF/LDF, wrong media,
# wrong legacy version, source file modifications and legacy source collisions.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BackupCopy)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$private=Join-Path $root '.private-parsian-staging-20261026'
$copy=Join-Path $private 'parsian-latest-20261026-1515.bak'
$backup=[IO.Path]::GetFullPath($BackupCopy)
if ($backup -cne $copy -or !(Test-Path -LiteralPath $backup -PathType Leaf)) {
  throw 'Only verified isolated latest BAK COPY is supported'
}
$expected='65E85D8BED539C4CB98D2A3F20416637524E5133CB7B940D6A4015A7CA368441'
if ((Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash -ne $expected) {
  throw 'Latest backup SHA-256 mismatch'
}
$name='MadarR17ParsianQA20261026'
$folder=Join-Path $private 'restored-sql-r17'
$mdf=Join-Path $folder 'MadarR17ParsianQA20261026_Data.mdf'
$ldf=Join-Path $folder 'MadarR17ParsianQA20261026_Log.ldf'
if ((Test-Path -LiteralPath $folder) -or (Test-Path -LiteralPath $mdf) -or
    (Test-Path -LiteralPath $ldf)) {throw 'Isolated SQL target exists; refusing overwrite'}
Add-Type -AssemblyName System.Data
$cn=New-Object System.Data.SqlClient.SqlConnection(
  'Server=localhost;Database=master;Integrated Security=True;Connect Timeout=8;Application Name=Madar-R17-Isolated-QA-Restore')
try {
  $cn.Open()
  $cmd=$cn.CreateCommand()
  $cmd.CommandText="SELECT CONVERT(varchar(40),SERVERPROPERTY('ProductVersion'))"
  if (![string]::Equals([string]$cmd.ExecuteScalar(),'8.00.194')) {
    throw 'Expected separately constrained known SQL Server 2000 Personal Edition'
  }
  $cmd.CommandText="SELECT COUNT(*) FROM master..sysdatabases WHERE name=N'$name'"
  if ([int]$cmd.ExecuteScalar() -ne 0) {throw 'QA SQL database already exists'}
  $escBak=$backup.Replace("'","''")
  $cmd.CommandTimeout=45
  $cmd.CommandText="RESTORE HEADERONLY FROM DISK=N'$escBak'"
  $reader=$cmd.ExecuteReader()
  try {
    if (!$reader.Read()) {throw 'No readable SQL backup'}
    if ([string]$reader['DatabaseName'] -cne 'db_1405' -or
        [int]$reader['BackupType'] -ne 1) {throw 'Unexpected source backup'}
  }finally {$reader.Close()}
  $cmd.CommandText="RESTORE FILELISTONLY FROM DISK=N'$escBak'"
  $reader=$cmd.ExecuteReader()
  $logical=@{}
  try {
    while ($reader.Read()) {$logical[[string]$reader['Type']]=[string]$reader['LogicalName']}
  }finally {$reader.Close()}
  if ($logical.Count -ne 2 -or $logical['D'] -cne 'db_13851_Data' -or
      $logical['L'] -cne 'db_13851_Log') {throw 'Unexpected physical backup files'}
  $cmd.CommandTimeout=90
  $cmd.CommandText="RESTORE VERIFYONLY FROM DISK=N'$escBak'"
  [void]$cmd.ExecuteNonQuery()
  [void](New-Item -ItemType Directory -Path $folder -ErrorAction Stop)
  $physicalD=$mdf.Replace("'","''")
  $physicalL=$ldf.Replace("'","''")
  $cmd.CommandTimeout=120
  $cmd.CommandText="RESTORE DATABASE [$name] FROM DISK=N'$escBak' WITH MOVE N'db_13851_Data' TO N'$physicalD', MOVE N'db_13851_Log' TO N'$physicalL', RECOVERY"
  [void]$cmd.ExecuteNonQuery()
  $cmd.CommandText="SELECT COUNT(*) FROM master..sysdatabases WHERE name=N'$name'"
  if ([int]$cmd.ExecuteScalar() -ne 1) {throw 'Isolated SQL restore did not create QA DB'}
  $cn.ChangeDatabase($name)
  $cmd=$cn.CreateCommand()
  $cmd.CommandText="SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'tbl[_]%' AND TABLE_TYPE='BASE TABLE'"
  $tables=[int]$cmd.ExecuteScalar()
  if ($tables -lt 90) {throw 'Restored QA database is missing expected vendor tables'}
  $counts=@{}
  foreach($t in @('tbl_Document','tbl_Factor','tbl_Goods','tbl_Check','tbl_Kol','tbl_Moeen','tbl_Tafsili')){
    $cmd.CommandText='SELECT COUNT(*) FROM dbo.['+$t+']'
    $counts[$t]=[int]$cmd.ExecuteScalar()
  }
  [ordered]@{restoredDb=$name;isolatedFileFolder=$folder;sourceBakSha256=$expected;
       restoredVendorTables=$tables;importantTableCounts=$counts;
       sourceProductionDatabaseUntouched=$true}|ConvertTo-Json -Depth 4 -Compress
}finally {$cn.Dispose()}
