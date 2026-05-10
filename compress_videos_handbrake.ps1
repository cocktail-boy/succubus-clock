param(
  [string]$SourceRoot = "video_outputs_seedance_1_5_pro",
  [string]$OutputRoot = "video_outputs_seedance_1_5_pro_handbrake",
  [string]$HandBrakeCli = "",
  [int]$Quality = 28,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Find-HandBrakeCli {
  param([string]$RequestedPath)

  if ($RequestedPath) {
    if (Test-Path -LiteralPath $RequestedPath) {
      return (Resolve-Path -LiteralPath $RequestedPath).Path
    }
    throw "HandBrakeCLI was not found at: $RequestedPath"
  }

  $pathCommand = Get-Command HandBrakeCLI -ErrorAction SilentlyContinue
  if ($pathCommand) {
    return $pathCommand.Source
  }

  $commonPaths = @(
    (Join-Path (Get-Location) "tools\handbrake-cli\HandBrakeCLI.exe"),
    "C:\Program Files\HandBrake\HandBrakeCLI.exe",
    "C:\Program Files (x86)\HandBrake\HandBrakeCLI.exe"
  )

  foreach ($path in $commonPaths) {
    if (Test-Path -LiteralPath $path) {
      return $path
    }
  }

  throw "HandBrakeCLI was not found. Install HandBrake or pass -HandBrakeCli C:\Path\To\HandBrakeCLI.exe"
}

$handBrakePath = Find-HandBrakeCli -RequestedPath $HandBrakeCli
$sourcePath = (Resolve-Path -LiteralPath $SourceRoot).Path
$outputPath = Join-Path (Get-Location) $OutputRoot
$reportPath = Join-Path $outputPath "compression_report.csv"
$logPath = Join-Path $outputPath "logs"

New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
New-Item -ItemType Directory -Force -Path $logPath | Out-Null

function Get-RelativePath {
  param(
    [string]$BasePath,
    [string]$TargetPath
  )

  $baseUri = New-Object System.Uri("$($BasePath.TrimEnd('\'))\")
  $targetUri = New-Object System.Uri($TargetPath)
  return [System.Uri]::UnescapeDataString(
    $baseUri.MakeRelativeUri($targetUri).ToString()
  ).Replace("/", "\")
}

$videos = Get-ChildItem -LiteralPath $sourcePath -Recurse -File -Filter *.mp4
if (!$videos) {
  throw "No MP4 files found in $sourcePath"
}

$results = foreach ($video in $videos) {
  $relativePath = Get-RelativePath -BasePath $sourcePath -TargetPath $video.FullName
  $destination = Join-Path $outputPath $relativePath
  $destinationDir = Split-Path -Parent $destination

  New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null

  if ((Test-Path -LiteralPath $destination) -and !$Force) {
    $outputFile = Get-Item -LiteralPath $destination
    [pscustomobject]@{
      file = $relativePath
      status = "skipped"
      original_bytes = $video.Length
      compressed_bytes = $outputFile.Length
      savings_percent = [math]::Round((1 - ($outputFile.Length / $video.Length)) * 100, 2)
    }
    continue
  }

  $tempDestination = "$destination.tmp.mp4"
  if (Test-Path -LiteralPath $tempDestination) {
    Remove-Item -LiteralPath $tempDestination -Force
  }

  $arguments = @(
    "--input", $video.FullName,
    "--output", $tempDestination,
    "--format", "av_mp4",
    "--optimize",
    "--encoder", "x264",
    "--encoder-preset", "medium",
    "--quality", "$Quality",
    "--rate", "24",
    "--cfr",
    "--audio", "none",
    "--crop-mode", "none"
  )

  Write-Host "Compressing $relativePath"
  $logFile = Join-Path $logPath "$($relativePath.Replace('\', '__')).log"
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $handBrakePath @arguments *> $logFile
  $exitCode = $LASTEXITCODE
  $ErrorActionPreference = $previousErrorActionPreference
  if ($exitCode -ne 0) {
    throw "HandBrakeCLI failed for $relativePath"
  }

  Move-Item -LiteralPath $tempDestination -Destination $destination -Force
  $outputFile = Get-Item -LiteralPath $destination

  [pscustomobject]@{
    file = $relativePath
    status = "encoded"
    original_bytes = $video.Length
    compressed_bytes = $outputFile.Length
    savings_percent = [math]::Round((1 - ($outputFile.Length / $video.Length)) * 100, 2)
  }
}

$results | Export-Csv -LiteralPath $reportPath -NoTypeInformation

$originalTotal = ($results | Measure-Object -Property original_bytes -Sum).Sum
$compressedTotal = ($results | Measure-Object -Property compressed_bytes -Sum).Sum
$savings = [math]::Round((1 - ($compressedTotal / $originalTotal)) * 100, 2)

Write-Host ""
Write-Host "Done."
Write-Host "Output: $outputPath"
Write-Host "Report: $reportPath"
Write-Host "Original total: $([math]::Round($originalTotal / 1MB, 2)) MB"
Write-Host "Compressed total: $([math]::Round($compressedTotal / 1MB, 2)) MB"
Write-Host "Savings: $savings%"
