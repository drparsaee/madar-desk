# Install ONLY a new standalone accounting R12 preview.
# Existing R5/R6 binaries, books, Parsian, Mohsensoft and user data untouched.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$name='Madar-Accounting-Mohsen-Premium-R12-20261025.exe'
$source=Join-Path $root ('release/'+$name)
$expected='402DA04FD0CD0D44B56C6C9E505EA401A394A6F04BDBDFFD1874D7AB20D719C4'
$target=Join-Path $env:LOCALAPPDATA 'Programs/Madar Accounting Mohsen R12'
$dataHub=Join-Path $env:LOCALAPPDATA 'Madar Accounting Companies R12'
$shortcutName='Madar Accounting R12 - MultiCompany.lnk'
$desktop=[Environment]::GetFolderPath('DesktopDirectory')
$menu=Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Madar Accounting Mohsen R12'
$links=@((Join-Path $desktop $shortcutName),(Join-Path $menu $shortcutName))
if(!(Test-Path -LiteralPath $source -PathType Leaf)){throw 'R12 executable not found'}
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expected){
  throw 'Executable checksum differs from verified R12 candidate'
}
if((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $dataHub)){
  throw 'R12 installation or company root already exists: refusing overwrite'
}
foreach($link in $links){
  if(Test-Path -LiteralPath $link){throw ('Refusing existing shortcut '+$link)}
}
if(Test-Path -LiteralPath $menu){
  throw 'R12 Start Menu location already exists'
}
$parent=Split-Path -Parent $target
$stage=Join-Path $parent ('Madar Accounting Mohsen R12.stage-'+[guid]::NewGuid().ToString('N'))
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
  $s.Description='Madar R12 independent per-company accounting and invoice editor'
  $s.Save()
}
if((Get-FileHash -LiteralPath (Join-Path $target $name) -Algorithm SHA256).Hash -ne $expected){
  throw 'Post-install application checksum mismatch'
}
Write-Output ('R12_INSTALL='+$target)
Write-Output ('R12_PRIVATE_COMPANY_HUB='+$dataHub)
Write-Output ('R12_DESKTOP='+$links[0])
Write-Output ('R12_MENU='+$links[1])
Write-Output 'R5_R6_AND_EXTERNAL_SOFTWARE_UNCHANGED=True'
