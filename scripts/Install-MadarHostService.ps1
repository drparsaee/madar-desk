# Administrator opt-in. No password is accepted by this script or SCM.
# First provision a NEW ProgramData authority interactively:
#   python madar_host_service.py provision --data-dir C:\ProgramData\MadarDeskHost\Data --owner admin
# Place a unique TLS pair at Data\tls\cert.pem and Data\tls\key.pem first.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [string]$HostExe,
    [string]$PythonExe,
    [string]$EntryScript,
    [string]$DataRoot = (Join-Path $env:ProgramData 'MadarDeskHost\Data'),
    [ValidateRange(1024, 65535)][int]$Port = 48370,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$name = 'MadarHost'
if ($env:OS -ne 'Windows_NT') { throw 'Windows SCM is required.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run elevated as administrator.'
}
$rootParent = [IO.Path]::GetFullPath((Join-Path $env:ProgramData 'MadarDeskHost')).TrimEnd('\')
$expected = [IO.Path]::GetFullPath((Join-Path $rootParent 'Data')).TrimEnd('\')
$resolvedData = [IO.Path]::GetFullPath($DataRoot).TrimEnd('\')
if (-not [string]::Equals($resolvedData, $expected, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'DataRoot must be the dedicated ProgramData\MadarDeskHost\Data authority.'
}
if (-not (Test-Path -LiteralPath $resolvedData -PathType Container)) {
    throw 'Provision new service authority first; no GUI APPDATA is imported.'
}
foreach ($directory in @($rootParent, $resolvedData, (Join-Path $resolvedData 'tls'))) {
    if (((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Reparse point in service authority is not permitted.'
    }
}
if (Test-Path -LiteralPath (Join-Path $resolvedData 'lan-connection.json')) {
    throw 'Refusing an existing GUI host/client config in service authority.'
}
foreach ($file in @('host-service-authority.json', 'lan-users.json',
                    'tls\cert.pem', 'tls\key.pem')) {
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedData $file) -PathType Leaf)) {
        throw ('Unprovisioned service authority: ' + $file)
    }
}
if ($HostExe -and ($PythonExe -or $EntryScript)) {
    throw 'Choose self-contained HostExe OR PythonExe with EntryScript.'
}
if (-not $HostExe -and (-not $PythonExe -or -not $EntryScript)) {
    throw 'Provide the self-contained MadarHost.exe via -HostExe.'
}
$runner = if ($HostExe) { (Resolve-Path -LiteralPath $HostExe).ProviderPath }
          else { (Resolve-Path -LiteralPath $PythonExe).ProviderPath }
$entry = if ($HostExe) { $null }
         else { (Resolve-Path -LiteralPath $EntryScript).ProviderPath }
foreach ($file in @($runner, $entry)) {
    if (-not $file) { continue }
    $trusted = $false
    foreach ($base in @($env:ProgramFiles, [Environment]::GetFolderPath('ProgramFilesX86'))) {
        if ($base -and $file.StartsWith(([IO.Path]::GetFullPath($base).TrimEnd('\') + '\'),
                                   [StringComparison]::OrdinalIgnoreCase)) {
            $trusted = $true
        }
    }
    if (-not $trusted) { throw 'Install reviewed Python and source under protected Program Files first.' }
}
if ($HostExe -and [IO.Path]::GetFileName($runner) -ne 'MadarHost.exe') {
    throw 'Unexpected service executable filename.'
}
if ($entry -and [IO.Path]::GetFileName($entry) -ne 'madar_host_service.py') {
    throw 'Unexpected Windows Service entry script.'
}
if (Get-Service -Name $name -ErrorAction SilentlyContinue) {
    throw 'MadarHost service already exists. Explicitly remove it before reinstalling.'
}
foreach ($rule in @('MadarHost-HTTPS', 'MadarHost-UDP-Discovery', 'MadarHost-UDP-Beacon')) {
    if (Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue) {
        throw ('Refusing to overwrite an existing firewall rule: ' + $rule)
    }
}

# Read-only validation. Never write to actual user APPDATA during install.
if ($HostExe) {
    & $runner check --data-dir $resolvedData
} else {
    & $runner $entry check --data-dir $resolvedData
}
if ($LASTEXITCODE -ne 0) { throw 'Authority and certificate check failed.' }
if ($ValidateOnly) {
    Write-Output 'Preflight successful, no service, ACL or system changes.'
    return
}
if (-not $PSCmdlet.ShouldProcess($name, 'Create automatic Windows background host')) { return }

# Native Python SCM dispatcher, available without pywin32. The ImagePath
# holds only source/certificate locations and port, NEVER passwords or tokens.
$quote = [char]34
$imagePath = $quote + $runner + $quote
if ($entry) { $imagePath += ' ' + $quote + $entry + $quote }
$imagePath += ' service --data-dir ' + $quote + $resolvedData + $quote + ' --port ' + $Port
$created = $false
try {
    & sc.exe create $name 'type=' 'own' 'start=' 'demand' 'obj=' 'NT SERVICE\MadarHost' 'DisplayName=' 'Madar Desk Background Host' 'binPath=' $imagePath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'SCM create failed.' }
    $created = $true
    & sc.exe sidtype $name unrestricted | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'SCM service SID configuration failed.' }

    # Only the dedicated ProgramData tree is modified. TLS private key,
    # salted password hashes, tasks and history remain private to this SID.
    & icacls.exe $rootParent /inheritance:r /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict service authority inheritance.' }
    & icacls.exe $rootParent /grant:r 'NT AUTHORITY\SYSTEM:(OI)(CI)F' 'BUILTIN\Administrators:(OI)(CI)F' 'NT SERVICE\MadarHost:(OI)(CI)M' /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Service account ACL setup failed.' }
    & sc.exe config $name 'start=' 'auto' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'SCM automatic startup failed.' }
    # Limit inbound service exposure to trusted private-subnet peers.
    # Apply firewall rules before the listener starts, not afterward.
    # Discovery uses UDP 48371 inbound and UDP 48372 outbound beacons.
    New-NetFirewallRule -Name 'MadarHost-HTTPS' -DisplayName 'Madar Host HTTPS' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet -ErrorAction Stop | Out-Null
    New-NetFirewallRule -Name 'MadarHost-UDP-Discovery' -DisplayName 'Madar Host UDP discovery' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 48371 -Profile Private -RemoteAddress LocalSubnet -ErrorAction Stop | Out-Null
    New-NetFirewallRule -Name 'MadarHost-UDP-Beacon' -DisplayName 'Madar Host UDP beacons' -Direction Outbound -Action Allow -Protocol UDP -RemotePort 48372 -Profile Private -RemoteAddress LocalSubnet -ErrorAction Stop | Out-Null
    & sc.exe start $name | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Service start failed; inspect Windows SCM event log.' }
    Write-Output 'MadarHost started as a dedicated virtual service account.'
    Write-Output 'Configure GUI as pinned-HTTPS LAN client and allow only trusted LAN peers in Windows Firewall.'
}
catch {
    if ($created) {
        foreach ($rule in @('MadarHost-HTTPS', 'MadarHost-UDP-Discovery', 'MadarHost-UDP-Beacon')) {
            Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
        }
        & sc.exe stop $name | Out-Null
        & sc.exe delete $name | Out-Null
    }
    throw
}
