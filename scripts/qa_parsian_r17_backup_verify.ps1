# Read-only MS SQL Server 2000 backup metadata/verify for an OWNED copied BAK.
# Does not restore, attach, ALTER, or inspect application rows.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BackupCopy)
$ErrorActionPreference='Stop'
$p=[IO.Path]::GetFullPath($BackupCopy)
if (!(Test-Path -LiteralPath $p -PathType Leaf) -or
    -not $p.Contains('.private-parsian-staging-20261026')) {
    throw 'Private copied BAK required'
}
Add-Type -AssemblyName System.Data
$cn=New-Object System.Data.SqlClient.SqlConnection(
    'Server=localhost;Database=master;Integrated Security=True;Connect Timeout=8;Application Name=Madar-R17-LatestBackup-ReadOnly')
try {
    $cn.Open()
    $sql=$cn.CreateCommand()
    $sql.CommandText="SELECT CONVERT(varchar(40),SERVERPROPERTY('ProductVersion'))"
    $version=[string]$sql.ExecuteScalar()
    if (!$version.StartsWith('8.')) {throw 'Unsupported SQL Server edition/version'}
    $esc=$p.Replace("'","''")
    $header=$cn.CreateCommand()
    $header.CommandTimeout=45
    $header.CommandText="RESTORE HEADERONLY FROM DISK=N'$esc'"
    $rd=$header.ExecuteReader()
    try {
        if (!$rd.Read()){throw 'No backup header'}
        $info=[ordered]@{DatabaseName=[string]$rd['DatabaseName'];
            BackupType=[int]$rd['BackupType'];
            BackupStartDate=[string]$rd['BackupStartDate'];
            BackupFinishDate=[string]$rd['BackupFinishDate'];
            ServerVersion=$version}
    }finally{$rd.Close()}
    $file=$cn.CreateCommand()
    $file.CommandTimeout=45
    $file.CommandText="RESTORE FILELISTONLY FROM DISK=N'$esc'"
    $rd=$file.ExecuteReader()
    $files=New-Object System.Collections.ArrayList
    try {
        while($rd.Read()){
            [void]$files.Add([ordered]@{LogicalName=[string]$rd['LogicalName'];
                 Type=[string]$rd['Type'];SizeBytes=[int64]$rd['Size']})
        }
    }finally{$rd.Close()}
    $verify=$cn.CreateCommand()
    $verify.CommandTimeout=120
    $verify.CommandText="RESTORE VERIFYONLY FROM DISK=N'$esc'"
    [void]$verify.ExecuteNonQuery()
    $info['VerifiedMedia']=$true
    $info['Files']=$files.ToArray()
    $info['BackupHash']=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash
    ConvertTo-Json -InputObject $info -Compress -Depth 4
}finally{$cn.Dispose()}
