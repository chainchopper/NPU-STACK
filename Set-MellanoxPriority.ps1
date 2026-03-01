# Set-MellanoxPriority.ps1
# Requires Run as Administrator

if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "Please run this script as an Administrator."
    Pause
    exit
}

Write-Host "Prioritizing Mellanox ConnectX-3 Adapter (Ethernet 7)..." -ForegroundColor Cyan
Set-NetIPInterface -InterfaceAlias "Ethernet 7" -InterfaceMetric 1
if ($?) {
    Write-Host "Successfully set Ethernet 7 metric to 1." -ForegroundColor Green
} else {
    Write-Host "Failed to set Ethernet 7 metric." -ForegroundColor Red
}

Write-Host "Lowering priority of Realtek 5GbE Adapter (Ethernet 4)..." -ForegroundColor Cyan
Set-NetIPInterface -InterfaceAlias "Ethernet 4" -InterfaceMetric 20
if ($?) {
    Write-Host "Successfully set Ethernet 4 metric to 20." -ForegroundColor Green
} else {
    Write-Host "Failed to set Ethernet 4 metric." -ForegroundColor Red
}

Write-Host "`nCurrent Interface Metrics:" -ForegroundColor Yellow
Get-NetIPInterface | Select-Object InterfaceAlias, InterfaceMetric | Where-Object { $_.InterfaceAlias -like "Ethernet*" }

Pause
