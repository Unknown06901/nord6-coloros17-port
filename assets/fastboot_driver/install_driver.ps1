# Run as Administrator. Installs nord6_fastboot.inf so Windows binds 18D1:D00D (bootloader AND fastbootd) automatically.
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir
Start-Transcript -Path (Join-Path $dir 'install_log.txt') -Force | Out-Null
try {
  $subj = 'CN=Nord6 port kit fastboot driver'
  $cert = Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -eq $subj } | Select-Object -First 1
  if (-not $cert) {
    $cert = New-SelfSignedCertificate -Subject $subj -Type CodeSigningCert -CertStoreLocation Cert:\LocalMachine\My -NotAfter (Get-Date).AddYears(20)
  }
  $cer = Join-Path $dir 'nord6_fastboot.cer'
  Export-Certificate -Cert $cert -FilePath $cer | Out-Null
  Import-Certificate -FilePath $cer -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
  Import-Certificate -FilePath $cer -CertStoreLocation Cert:\LocalMachine\TrustedPublisher | Out-Null
  $cat = Join-Path $dir 'nord6_fastboot.cat'
  if (Test-Path $cat) { Remove-Item $cat }
  $tmp = Join-Path $env:TEMP 'nord6_fb_cat'; Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory $tmp | Out-Null
  Copy-Item (Join-Path $dir 'nord6_fastboot.inf') $tmp
  New-FileCatalog -Path $tmp -CatalogFilePath $cat -CatalogVersion 1.0 | Out-Null
  $sig = Set-AuthenticodeSignature -FilePath $cat -Certificate $cert -HashAlgorithm SHA256
  Write-Host "catalog signature: $($sig.Status)"
  pnputil /add-driver (Join-Path $dir 'nord6_fastboot.inf') /install
  Write-Host "pnputil exit: $LASTEXITCODE"
  pnputil /scan-devices | Out-Null
} catch { Write-Host "ERROR: $_" }
Stop-Transcript | Out-Null
