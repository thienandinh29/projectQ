param(
  [Parameter(Mandatory = $true)][string]$WindowTitle,
  [ValidateRange(15, 300)][int]$Seconds = 120
)

# Run manually after the browser checklist passes. Capture only the named demo window.
$ErrorActionPreference = 'Stop'
$ffmpegCommand = Get-Command ffmpeg -ErrorAction Stop
$recordingPath = Join-Path $PSScriptRoot 'NodeTrail-demo.mp4'
if (Test-Path -LiteralPath $recordingPath) {
  throw 'NodeTrail-demo.mp4 already exists. Rename the existing recording before running again.'
}
& $ffmpegCommand.Source -n -f gdigrab -framerate 15 -i "title=$WindowTitle" -t $Seconds -an -c:v libx264 -preset veryfast -crf 22 -vf 'scale=trunc(iw/2)*2:trunc(ih/2)*2' -pix_fmt yuv420p -movflags +faststart $recordingPath
if ($LASTEXITCODE -ne 0) { throw 'Recording failed. Inspect ffmpeg output before treating this as a delivered video.' }
Write-Output $recordingPath
