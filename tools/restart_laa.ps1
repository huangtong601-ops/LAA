# 重启 LAA(MFAAvalonia) 以加载最新内容
$ErrorActionPreference = 'SilentlyContinue'
Get-Process -Name MFAAvalonia -ErrorAction SilentlyContinue | Stop-Process -Force
$agents = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'E:\\LAA\\MaaBoilerplate\\agent\\main.py' }
foreach ($agent in $agents) {
    Stop-Process -Id $agent.ProcessId -Force
}
Start-Sleep -Seconds 2
$env:TEMP='E:\LAA\.tmp'; $env:TMP='E:\LAA\.tmp'; New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$env:DOTNET_ROOT='E:\LAA\.dotnet'; $env:DOTNET_MULTILEVEL_LOOKUP='0'; $env:PATH="E:\LAA\.dotnet;$env:PATH"
Start-Process -FilePath 'E:\LAA\MaaBoilerplate\gui\MFAAvalonia.exe' -WorkingDirectory 'E:\LAA\MaaBoilerplate\gui'
Write-Output 'LAA 已重启。'
