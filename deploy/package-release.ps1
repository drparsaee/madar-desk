param(
  [string]$OutputDirectory = ""
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $root 'release' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

Write-Host 'Building the web-only production bundle...'
Push-Location $root
try {
  & npm.cmd run web:build
  if ($LASTEXITCODE -ne 0) { throw "web:build failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$stage = Join-Path ([IO.Path]::GetTempPath()) ("madar-web-release-" + [guid]::NewGuid().ToString('N'))
$verify = Join-Path ([IO.Path]::GetTempPath()) ("madar-web-verify-" + [guid]::NewGuid().ToString('N'))
$zip = Join-Path $OutputDirectory ("madar-web-pwa-$stamp.zip")
New-Item -ItemType Directory -Path $stage | Out-Null
try {
  foreach ($entry in @(
    @{ Source = (Join-Path $root 'dist-web'); Destination = (Join-Path $stage 'www') },
    @{ Source = (Join-Path $root 'server'); Destination = (Join-Path $stage 'server') },
    @{ Source = $PSScriptRoot; Destination = (Join-Path $stage 'deploy') },
    @{ Source = (Join-Path $root 'docs\api'); Destination = (Join-Path $stage 'docs\api') },
    @{ Source = (Join-Path $root 'docs\deployment'); Destination = (Join-Path $stage 'docs\deployment') }
  )) {
    if (-not (Test-Path -LiteralPath $entry.Source)) { throw "Release input missing: $($entry.Source)" }
    $parent = Split-Path -Parent $entry.Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $entry.Source -Destination $entry.Destination -Recurse
  }

  $hashLines = foreach ($file in Get-ChildItem -LiteralPath $stage -File -Recurse | Sort-Object FullName) {
    $relative = $file.FullName.Substring($stage.Length).TrimStart('\','/').Replace('\','/')
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relative"
  }
  Set-Content -LiteralPath (Join-Path $stage 'SHA256SUMS.txt') -Value $hashLines -Encoding ASCII
  if (Test-Path -LiteralPath $zip) { throw "Refusing to overwrite $zip" }
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal

  Expand-Archive -LiteralPath $zip -DestinationPath $verify
  foreach ($line in Get-Content -LiteralPath (Join-Path $verify 'SHA256SUMS.txt')) {
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Malformed release checksum manifest.' }
    $expected = $Matches[1]
    $relative = $Matches[2].Replace('/', [IO.Path]::DirectorySeparatorChar)
    $file = Join-Path $verify $relative
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Release member missing: $relative" }
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "Release checksum mismatch: $relative" }
  }
  $zipHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
  Set-Content -LiteralPath "$zip.sha256" -Value "$zipHash  $(Split-Path -Leaf $zip)" -Encoding ASCII
  Write-Host "Verified web deployment package: $zip"
  Write-Host "SHA-256: $zipHash"
} finally {
  if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
  if (Test-Path -LiteralPath $verify) { Remove-Item -LiteralPath $verify -Recurse -Force }
}
