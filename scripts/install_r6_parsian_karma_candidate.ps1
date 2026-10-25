# Side-by-side deployment of FR3-derived print candidate.
# NEVER modifies R5 binaries, finance books, Parsian install or live processes.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$project=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$source=Join-Path $project 'release/Madar-Accounting-Parsian-Karma-R6-20261025.exe'
$destination=Join-Path $env:LOCALAPPDATA 'Programs/Madar Accounting Karma R6'
$accountingData=Join-Path $env:LOCALAPPDATA 'Madar Suite Data R5/Accounting'
$exeName='Madar-Accounting-Parsian-Karma-R6-20261025.exe'
$launchName='Launch-Madar-Accounting-Karma-R6.ps1'
$linkName='Madar Accounting R6 - Parsian Karma.lnk'
$menu=Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Madar Accounting Karma R6'
$desktop=[Environment]::GetFolderPath('DesktopDirectory')
$links=@((Join-Path $desktop $linkName),(Join-Path $menu $linkName))
$expected='EFBEA9458CAF36C9F9A9E8BC2D4F3670D6B519A74947F21BC0025C47A50CC3C5'
if(!(Test-Path -LiteralPath $source -PathType Leaf)){throw 'Expected R6 candidate missing'}
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expected){throw 'R6 candidate checksum mismatch'}
if(!(Test-Path -LiteralPath $accountingData -PathType Container)){throw 'Dedicated R5 accounting book missing'}
if(Test-Path -LiteralPath $destination){throw 'R6 installation already exists: refuse overwrite'}
foreach($link in $links){if(Test-Path -LiteralPath $link){throw ('Refusing existing shortcut '+$link)}}
$parent=Split-Path -Parent $destination
$stage=Join-Path $parent ('Madar Accounting Karma R6.stage-'+[guid]::NewGuid().ToString('N'))
if(Test-Path -LiteralPath $stage){throw 'Staging path collision'}
New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
try{
  Copy-Item -LiteralPath $source -Destination (Join-Path $stage $exeName) -ErrorAction Stop
  if((Get-FileHash -LiteralPath (Join-Path $stage $exeName) -Algorithm SHA256).Hash -ne $expected){
    throw 'Staging checksum mismatch'
  }
  $launch=@'
$ErrorActionPreference='Stop'
$book=Join-Path $env:LOCALAPPDATA 'Madar Suite Data R5\Accounting'
$app=Join-Path $PSScriptRoot 'Madar-Accounting-Parsian-Karma-R6-20261025.exe'
$running=@(Get-CimInstance Win32_Process | Where-Object {
  $_.Name -in @('Madar-Accounting-R5.exe','Madar-Accounting-Parsian-Karma-R6-20261025.exe')
})
if($running.Count -gt 0){
  Add-Type -AssemblyName PresentationFramework
  [System.Windows.MessageBox]::Show(
    'ابتدا پنجره حسابداری مدار R5 یا R6 را ببندید. اجرای همزمان دو نسخه روی یک دفتر مالی مجاز نیست.',
    'مدار - حسابداری پارسیان') | Out-Null
  exit 2
}
if(!(Test-Path -LiteralPath $book -PathType Container)){throw 'Financial book missing'}
Start-Process -FilePath $app -WorkingDirectory $PSScriptRoot -ArgumentList @('--data-dir',('"' + $book + '"'))
'@
  [IO.File]::WriteAllText((Join-Path $stage $launchName),$launch,[Text.UTF8Encoding]::new($true))
  [IO.Directory]::Move($stage,$destination)
}catch{
  if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Recurse -Force}
  throw
}
New-Item -ItemType Directory -Path $menu -Force | Out-Null
$ws=New-Object -ComObject WScript.Shell
foreach($link in $links){
  $s=$ws.CreateShortcut($link)
  $s.TargetPath=(Join-Path $PSHOME 'powershell.exe')
  $s.Arguments='-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+(Join-Path $destination $launchName)+'"'
  $s.WorkingDirectory=$destination
  $s.IconLocation=(Join-Path $destination $exeName)+',0'
  $s.Description='Madar standalone accounting, Parsian Karma FR3-derived invoice print layout'
  $s.Save()
}
if((Get-FileHash -LiteralPath (Join-Path $destination $exeName) -Algorithm SHA256).Hash -ne $expected){
  throw 'Post-install checksum mismatch'
}
Write-Output ('INSTALL_R6_READY='+$destination)
Write-Output ('R5_DATA_UNCHANGED='+$accountingData)
Write-Output ('DESKTOP_SHORTCUT='+$links[0])
Write-Output ('START_MENU_SHORTCUT='+$links[1])
Write-Output 'NOTE=Close R5 before clicking R6 shortcut; launcher blocks duplicate sessions.'
