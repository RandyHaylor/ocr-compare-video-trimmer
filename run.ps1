# Windows launcher. Installs uv if needed; uv then installs Python and the dependencies.
# No arguments opens the web UI; with arguments it runs the command line tool.
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

uv run --project $PSScriptRoot ocr-compare-video-trimmer @args
exit $LASTEXITCODE
