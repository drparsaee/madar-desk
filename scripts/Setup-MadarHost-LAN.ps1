# One-time opt-in setup for the dedicated MadarHost Windows background service.
# Run from the EXTRACTED delivery folder in an elevated PowerShell window.
# Creates a NEW authority only. Never reads, copies, or deletes existing GUI data.
[CmdletBinding()]
param([switch]$ValidateOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceExe = Join-Path $here 'MadarHost.exe'
$openssl = Join-Path $here 'tools\openssl.exe'
$opensslConfig = Join-Path $here 'tools\openssl.cnf'
$serviceScript = Join-Path $here 'Install-MadarHostService.ps1'
$installedDir = Join-Path $env:ProgramFiles 'MadarHost'
$installedExe = Join-Path $installedDir 'MadarHost.exe'
$authority = Join-Path $env:ProgramData 'MadarDeskHost\Data'
$tls = Join-Path $authority 'tls'
$cert = Join-Path $tls 'cert.pem'
$privateKey = Join-Path $tls 'key.pem'

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run Start-MadarHost-Setup.cmd as Administrator.'
    }
}
function IsPrivateIPv4([string]$value) {
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($value, [ref]$parsed) -or
        $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        return $false
    }
    $bytes = $parsed.GetAddressBytes()
    return ($bytes[0] -eq 10) -or
           ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
           ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
}

if ($env:OS -ne 'Windows_NT') {throw 'MadarHost requires Windows.'}
if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {throw 'MadarHost.exe is missing.'}
if (-not (Test-Path -LiteralPath $openssl -PathType Leaf)) {throw 'Bundled OpenSSL missing.'}
if (-not (Test-Path -LiteralPath $opensslConfig -PathType Leaf)) {throw 'Bundled OpenSSL config missing.'}
if (-not (Test-Path -LiteralPath $serviceScript -PathType Leaf)) {throw 'Service installer missing.'}
if ($ValidateOnly) {
    Write-Host 'Package files present; installation and account creation NOT attempted.'
    return
}
Assert-Admin

# Refuse existing installations/authorities rather than silently replacing user data.
if (Get-Service -Name 'MadarHost' -ErrorAction SilentlyContinue) {
    throw 'MadarHost service already installed. This setup never overwrites it.'
}
if (Test-Path -LiteralPath $authority) {
    throw 'A MadarHost authority already exists. Setup stopped to preserve data.'
}
if (Test-Path -LiteralPath $installedExe) {
    throw 'A MadarHost binary is already installed. Setup stopped to preserve it.'
}
if (Get-ChildItem -LiteralPath $here -File -Filter '*.pem' -ErrorAction SilentlyContinue) {
    throw 'Do not distribute host private keys in the installation folder.'
}

$profiles = @(Get-NetConnectionProfile -ErrorAction Stop |
    Where-Object {$_.NetworkCategory -eq 'Private'})
if (-not $profiles.Count) {
    throw 'Change the trusted office LAN to a Private network in Windows Settings first.'
}
$candidate = @(
    Get-NetIPConfiguration -ErrorAction Stop |
    Where-Object {$_.IPv4DefaultGateway -and $_.IPv4Address -and
        ($profiles.InterfaceIndex -contains $_.InterfaceIndex)} |
    ForEach-Object {$_.IPv4Address.IPAddress} |
    Where-Object {IsPrivateIPv4 $_} |
    Select-Object -Unique
)
Write-Host 'Trusted Private LAN candidates:' ($candidate -join ', ')
$defaultIP = if ($candidate.Count -eq 1) {$candidate[0]} else {''}
$ip = Read-Host ("Host IPv4 to advertise in TLS certificate [{0}]" -f $defaultIP)
if (-not $ip) {$ip = $defaultIP}
if (-not (IsPrivateIPv4 $ip)) {throw 'Enter a valid PRIVATE IPv4 address from the trusted LAN.'}
if (-not ($candidate -contains $ip)) {throw 'IPv4 is not on an active Private network with a gateway.'}

$adminUser = Read-Host 'New Madar LAN admin username (3-40 ASCII chars)'
if ($adminUser -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{2,39}$') {
    throw 'Invalid admin username.'
}
Write-Host 'A NEW empty host authority will be created at' $authority
Write-Host 'Existing per-user Madar tasks and account data will NOT be imported.'
Write-Host 'The host requires an interactive password (minimum 10 characters).'
$approval = Read-Host 'Type INSTALL to proceed'
if ($approval -cne 'INSTALL') {throw 'No installation performed.'}

# The key never touches the USB or client machine. Windows ACLs are sealed
# by Install-MadarHostService.ps1 before the service is started.
New-Item -ItemType Directory -Path $tls -Force -ErrorAction Stop | Out-Null
# Lock the TLS directory BEFORE writing an unencrypted private key. The
# dedicated service installer later additionally locks the entire authority.
& icacls.exe $tls /inheritance:r | Out-Null
if ($LASTEXITCODE -ne 0) {throw 'Could not remove inherited TLS folder ACL.'}
& icacls.exe $tls /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) {throw 'Could not restrict TLS folder access.'}
# OpenSSL from Git for Windows expects a Git install tree by default.
# Passing its local config explicitly makes this USB package standalone.
$opensslError = Join-Path $env:TEMP ('madar-host-openssl-' + [guid]::NewGuid().ToString('N') + '.log')
$oldErrorAction = $ErrorActionPreference
try {
    # Key generation progress is printed to stderr even on success.
    $ErrorActionPreference = 'Continue'
    & $openssl req -config $opensslConfig -x509 -newkey rsa:3072 -noenc `
        -sha256 -days 825 -subj '/CN=MadarHost' `
        -addext ("subjectAltName=IP:{0},DNS:localhost" -f $ip) `
        -addext 'basicConstraints=critical,CA:FALSE' `
        -addext 'extendedKeyUsage=serverAuth' `
        -keyout $privateKey -out $cert 2> $opensslError
    $opensslResult = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $oldErrorAction
    Remove-Item -LiteralPath $opensslError -Force -ErrorAction SilentlyContinue
}
if ($opensslResult -ne 0 -or -not (Test-Path -LiteralPath $privateKey) -or
    -not (Test-Path -LiteralPath $cert)) {
    throw 'TLS generation failed. No host service has been registered.'
}
& $sourceExe provision --data-dir $authority --owner $adminUser
if ($LASTEXITCODE -ne 0) {
    throw 'Host provision failed. No host service has been registered.'
}
& $sourceExe check --data-dir $authority
if ($LASTEXITCODE -ne 0) {throw 'Host authority validation failed.'}

New-Item -ItemType Directory -Path $installedDir -Force -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath $sourceExe -Destination $installedExe -ErrorAction Stop
& $serviceScript -HostExe $installedExe -DataRoot $authority -Port 48370 -Confirm:$false
if (-not $?) {throw 'Host Windows Service installation failed.'}
$state = Get-Service -Name 'MadarHost' -ErrorAction Stop
if ($state.Status -ne 'Running') {throw 'Host service is not running.'}

$fingerprint = & $openssl x509 -in $cert -noout -fingerprint -sha256
if ($LASTEXITCODE -ne 0) {throw 'Could not read host TLS fingerprint.'}
Write-Host ''
Write-Host 'MADAR HOST INSTALLED AND RUNNING.'
Write-Host ("HOST URL: https://{0}:48370" -f $ip)
Write-Host ($fingerprint -join ' ')
Write-Host 'On the client PC: Madar > Network > Find Host.'
Write-Host 'Compare fingerprint here independently before sending any credentials.'
Write-Host 'If Windows network/firewall prevents discovery, diagnose LAN; do not disable TLS.'
