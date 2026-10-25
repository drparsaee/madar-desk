# Install ONLY a new standalone accounting R10 preview.
# Existing R5/R6 binaries, books, Parsian, Mohsensoft and user data untouched.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$name='Madar-Accounting-Mohsen-UX-R10-20261025.exe'
$source=Join-Path $root ('release/'+$name)
$expected='7F0E64D14B2CFCA72359C1882FEB55317D54BD6379DBA557A4C4DA3A3028890C'
$target=Join-Path $env:LOCALAPPDATA 'Programs/Madar Accounting Mohsen R10'
$dataHub=Join-Path $env:LOCALAPPDATA 'Madar Accounting Companies R10'
$shortcutName='Madar Accounting R10 - MultiCompany.lnk'
$desktop=[Environment]::GetFolderPath('DesktopDirectory')
$menu=Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Madar Accounting Mohsen R10'
$links=@((Join-Path $desktop $shortcutName),(Join-Path $menu $shortcutName))
if(!(Test-Path -LiteralPath $source -PathType Leaf)){throw 'R10 executable not found'}
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expected){
  throw 'Executable checksum differs from verified R10 candidate'
}
if((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $dataHub)){
  throw 'R10 installation or company root already exists: refusing overwrite'
}
foreach($link in $links){
  if(Test-Path -LiteralPath $link){throw ('Refusing existing shortcut '+$link)}
}
if(Test-Path -LiteralPath $menu){
  throw 'R10 Start Menu location already exists'
}
$parent=Split-Path -Parent $target
$stage=Join-Path $parent ('Madar Accounting Mohsen R10.stage-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
try{
  Copy-Item -LiteralPath $source -Destination (Join-Path $stage $name) -ErrorAction Stop
  if((Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash -ne $expected){
    throw 'Staged application failed SHA-256 validation'
  }
  [IO.Directory]::Move($stage,$target)
}catch{
  if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Recurse -Force}
  throw
}
# New, empty per-company data root. Never migrate/merge an existing ledger.
New-Item -ItemType Directory -Path $dataHub -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path $menu -ErrorAction Stop | Out-Null
$ws=New-Object -ComObject WScript.Shell
foreach($link in $links){
  $s=$ws.CreateShortcut($link)
  $s.TargetPath=Join-Path $target $name
  $s.Arguments='--companies-dir "'+$dataHub+'"'
  $s.WorkingDirectory=$target
  $s.IconLocation=(Join-Path $target $name)+',0'
  $s.Description='Madar R10 independent per-company accounting and invoice editor'
  $s.Save()
}
if((Get-FileHash -LiteralPath (Join-Path $target $name) -Algorithm SHA256).Hash -ne $expected){
  throw 'Post-install application checksum mismatch'
}
Write-Output ('R10_INSTALL='+$target)
Write-Output ('R10_PRIVATE_COMPANY_HUB='+$dataHub)
Write-Output ('R10_DESKTOP='+$links[0])
Write-Output ('R10_MENU='+$links[1])
Write-Output 'R5_R6_AND_EXTERNAL_SOFTWARE_UNCHANGED=True'
