param(
    [string]$SourceDir = (Join-Path $PSScriptRoot '..\..\..\MFAAvalonia-src'),
    [string]$DotnetExe = (Join-Path $PSScriptRoot '..\..\..\.tmp\mfa-build\.dotnet-sdk\dotnet.exe')
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$source = (Resolve-Path $SourceDir).Path
$dotnet = (Resolve-Path $DotnetExe).Path
$patch = Join-Path $PSScriptRoot 'laa-chip-filter.patch'

git -C $source apply --check $patch 2>$null
if ($LASTEXITCODE -eq 0) {
    git -C $source apply $patch
} else {
    git -C $source apply --reverse --check $patch 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'MFAAvalonia source does not match the LAA patch base.'
    }
}

$buildRoot = Join-Path (Split-Path $projectRoot -Parent) '.tmp\mfa-build'
$env:DOTNET_CLI_HOME = Join-Path (Split-Path $projectRoot -Parent) '.dotnet-home'
$env:NUGET_PACKAGES = Join-Path $buildRoot 'nuget'
$env:TEMP = Join-Path $buildRoot 'temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:DOTNET_CLI_HOME, $env:NUGET_PACKAGES, $env:TEMP | Out-Null

& $dotnet restore (Join-Path $source 'MFAAvalonia.Desktop\MFAAvalonia.Desktop.csproj') -r win-x64
& $dotnet build (Join-Path $source 'MFAAvalonia.Desktop\MFAAvalonia.Desktop.csproj') -c Release -r win-x64 --no-restore

$running = Get-Process -Name 'MFAAvalonia' -ErrorAction SilentlyContinue
if ($running) {
    throw 'Close LAA before installing the rebuilt UI core.'
}

$builtCore = Join-Path $source 'bin\AnyCPU\Release\MFAAvalonia.Core.dll'
$targetCore = Join-Path $projectRoot 'gui\libs\MFAAvalonia.Core.dll'
Copy-Item -LiteralPath $builtCore -Destination $targetCore -Force
Write-Output "Installed customized UI core: $targetCore"

