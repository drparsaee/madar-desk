# Opt-in SCM removal only. Never delete tasks, credentials, keys or backups.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$name = 'MadarHost'
if ($env:OS -ne 'Windows_NT') { throw 'Windows SCM is required.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run elevated as administrator.'
}
$service = Get-Service -Name $name -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Output 'MadarHost is not registered. No changes performed.'
    return
}
if (-not $PSCmdlet.ShouldProcess($name, 'Stop and remove SCM service, preserve data')) { return }
if ($service.Status -ne 'Stopped') {
    Stop-Service -Name $name -ErrorAction Stop
    $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
}
& sc.exe delete $name | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'SCM rejected service removal.' }
foreach ($rule in @('MadarHost-HTTPS', 'MadarHost-UDP-Discovery', 'MadarHost-UDP-Beacon')) {
    Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction Stop
}
Write-Output 'MadarHost service removed. Dedicated ProgramData remains intact.'
