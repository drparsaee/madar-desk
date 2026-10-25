# Install ONLY a new standalone accounting R7 preview.
# Existing R5/R6 binaries, books, Parsian, Mohsensoft and user data untouched.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$name='Madar-Accounting-Mohsen-UX-R7-20261025.exe'
$source=Join-Path $root ('release/'+$name)
$expected='4832F525D2F41E7ED2A1F2F7FBF808F7C96FFF36F387AB68C73F1E99429A3DD0'
$target=Join-Path $env:LOCALAPPDATA 'Programs/Madar Accounting Mohsen R7'
$dataHub=Join-Path $env:LOCALAPPDATA 'Madar Accounting Companies R7'
$shortcutName='Madar Accounting R7 - MultiCompany.lnk'
$desktop=[Environment]::GetFolderPath('DesktopDirectory')
$menu=Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Madar Accounting Mohsen R7'
$links=@((Join-Path $desktop $shortcutName),(Join-Path $menu $shortcutName))
if(!(Test-Path -LiteralPath $source -PathType Leaf)){throw 'R7 executable not found'}
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expected){
  throw 'Executable checksum differs from verified R7 candidate'
}
if((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $dataHub)){
  throw 'R7 installation or company root already exists: refusing overwrite'
}
foreach($link in $links){
  if(Test-Path -LiteralPath $link){throw ('Refusing existing shortcut '+$link)}
}
if(Test-Path -LiteralPath $menu){
  throw 'R7 Start Menu location already exists'
}
$parent=Split-Path -Parent $target
$stage=Join-Path $parent ('Madar Accounting Mohsen R7.stage-'+[guid]::NewGuid().ToString('N'))
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
  $s.Description='Madar R7 independent per-company accounting and invoice editor'
  $s.Save()
}
if((Get-FileHash -LiteralPath (Join-Path $target $name) -Algorithm SHA256).Hash -ne $expected){
  throw 'Post-install application checksum mismatch'
}
Write-Output ('R7_INSTALL='+$target)
Write-Output ('R7_PRIVATE_COMPANY_HUB='+$dataHub)
Write-Output ('R7_DESKTOP='+$links[0])
Write-Output ('R7_MENU='+$links[1])
Write-Output 'R5_R6_AND_EXTERNAL_SOFTWARE_UNCHANGED=True'
