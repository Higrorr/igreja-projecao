# configurar.ps1 - Instala o Sistema de Projecao neste PC.
# Execute com "Excluir com o botao direito > Executar com o PowerShell".
# Eleva sozinho para admin (cria regra de firewall) e pede confirmacao UAC.

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Raiz = $PSScriptRoot
if (-not (Test-Path (Join-Path $Raiz "igreja.exe"))) {
    Write-Host "ERRO: igreja.exe nao foi encontrado ao lado deste script." -ForegroundColor Red
    Write-Host "Coloque o arquivo configurar.ps1 na MESMA pasta de igreja.exe."
    Read-Host "Pressione Enter para sair"
    exit 1
}

# --- Auto-elevacao (UAC) ---------------------------------------------------
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $admin) {
    Write-Host "Pedindo permissoes de administrador (UAC)..." -ForegroundColor Yellow
    try {
        Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", "`"$PSCommandPath`""
        )
    } catch {
        Write-Host "Voce cancelou a elevacao. A regra de firewall NAO sera criada." -ForegroundColor Red
        Read-Host "Pressione Enter para sair"
        exit 1
    }
    exit 0
}

Write-Host ""
Write-Host "=== Configurando o Sistema de Projecao ===" -ForegroundColor Cyan

# --- Pre-requisitos (apenas avisos) ---------------------------------------
$pptPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\POWERPNT.EXE"
if (Test-Path $pptPath) {
    Write-Host "[OK] PowerPoint instalado (necessario para projetar slides)." -ForegroundColor Green
} else {
    Write-Host "[AVISO] PowerPoint nao encontrado. Slides/Biblia/Harpa nao abrirao." -ForegroundColor Yellow
}

$chrome = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
$edge = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) {
    Write-Host "[OK] Chrome encontrado (usado para os playbacks em tela cheia)." -ForegroundColor Green
} elseif ($edge) {
    Write-Host "[INFO] Chrome nao encontrado; usarei o Edge para playbacks." -ForegroundColor Yellow
} else {
    Write-Host "[AVISO] Nenhum navegador Chrome/Edge encontrado." -ForegroundColor Yellow
}

# --- Regra de firewall (porta 5000) ---------------------------------------
$regra = "igreja-projecao"
if (Get-NetFirewallRule -DisplayName $regra -ErrorAction SilentlyContinue) {
    Write-Host "[OK] Regra de firewall ja existe." -ForegroundColor Green
} else {
    try {
        New-NetFirewallRule -DisplayName $regra -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort 5000 | Out-Null
        Write-Host "[OK] Porta 5000 liberada no firewall." -ForegroundColor Green
    } catch {
        Write-Host "[ERRO] Nao consegui criar a regra de firewall: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# --- Atalhos ---------------------------------------------------------------
$script:shell = New-Object -ComObject WScript.Shell

function Nova-Atalho([string]$Destino, [string]$Base, [string]$Nome) {
    $alvo = Join-Path $Base $Nome
    $lnk = $shell.CreateShortcut($alvo)
    $lnk.TargetPath = Join-Path $Raiz "igreja.exe"
    $lnk.WorkingDirectory = $Raiz
    $lnk.Description = "Sistema de Projecao - Libere o servidor e projete"
    $lnk.Save()
    if (Test-Path $alvo) { Write-Host "[OK] Atalho criado: $Destino" -ForegroundColor Green }
}

try {
    $desktop = [Environment]::GetFolderPath("Desktop")
    Nova-Atalho "area de trabalho" $desktop "Projecao Igreja.lnk"
} catch {
    Write-Host "[AVISO] Nao criei o atalho na area de trabalho: $($_.Exception.Message)" -ForegroundColor Yellow
}

try {
    $startup = [Environment]::GetFolderPath("Startup")
    Nova-Atalho "inicializacao do Windows" $startup "Projecao Igreja.lnk"
    Write-Host "[OK] O sistema vai INICIAR JUNTO COM O WINDOWS (atalho na pasta de inicializacao)." -ForegroundColor Green
} catch {
    Write-Host "[AVISO] Nao criei o atalho de inicializacao: $($_.Exception.Message)" -ForegroundColor Yellow
}

# --- IP local + resumo ------------------------------------------------------
$ip = $null
try {
    $s = New-Object Net.Sockets.UdpClient
    $s.Connect("8.8.8.8", 80)
    $ip = $s.Client.LocalEndPoint.Address.ToString()
    $s.Close()
} catch { }
if (-not $ip) { $ip = (Test-Connection -ComputerName $env:COMPUTERNAME -Count 1).Ipv4Address.IPAddressToString }

Write-Host ""
Write-Host "=== Pronto! ===" -ForegroundColor Green
Write-Host "1) Abra o atalho 'Projecao Igreja' (area de trabalho)."
Write-Host "   .: A janela mostrara o endereco do servidor"
Write-Host "2) No CELULAR, entre na MESMA rede Wi-Fi deste PC e acesse:"
Write-Host "   http://${ip}:5000" -ForegroundColor Cyan
Write-Host "3) Para parar: botao 'Parar servidor' na janela de controle."
Write-Host "   (Ao ligar o PC, o sistema abre sozinho.)"
Write-Host ""
Read-Host "Pressione Enter para fechar"