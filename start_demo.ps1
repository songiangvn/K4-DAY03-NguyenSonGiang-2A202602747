# =============================================================================
# 🚀 KHỞI ĐỘNG DEMO TRỢ LÝ SỨC KHỎE VINMEC (API Agent + Giao diện Web)
#
# Cách dùng:
#     .\start_demo.ps1              # dùng LLM thật theo cấu hình trong .env
#     .\start_demo.ps1 -Mock        # ép chạy Mock offline, không tốn API quota
#
# Script mở 2 tiến trình nền (API Python cổng 8080, Next.js cổng 3000),
# rồi tự mở trình duyệt. Nhấn Ctrl+C để dừng cả hai.
# =============================================================================

param(
    [switch]$Mock,
    [switch]$Force,      # Tu dong dung tien trinh dang chiem cong, khong hoi lai
    [int]$ApiPort = 8080,
    [int]$WebPort = 3000
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

# -----------------------------------------------------------------------------
# Kiem tra cong co dang bi chiem khong (tranh loi EADDRINUSE khi demo)
# -----------------------------------------------------------------------------
function Resolve-PortConflict {
    param([int]$Port, [string]$Label)

    $pids = @(netstat -ano |
        Select-String ":$Port\s" |
        Select-String 'LISTENING' |
        ForEach-Object { ($_ -split '\s+')[-1] } |
        Select-Object -Unique)

    if (-not $pids) { return $true }

    foreach ($processId in $pids) {
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.ProcessName } else { 'khong ro' }
        Write-Host "[!] Cong $Port ($Label) dang bi chiem boi PID $processId ($name)" -ForegroundColor Yellow
    }

    $answer = 'y'
    if (-not $Force) {
        Write-Host "    Dung tien trinh do de tiep tuc? [Y/n] " -ForegroundColor Yellow -NoNewline
        $answer = Read-Host
        if ([string]::IsNullOrWhiteSpace($answer)) { $answer = 'y' }
    }

    if ($answer -notmatch '^[yY]') {
        Write-Host "    Da bo qua. Hay chay lai voi cong khac, vi du:" -ForegroundColor Red
        Write-Host "    .\start_demo.ps1 -ApiPort 8090 -WebPort 3001" -ForegroundColor Red
        return $false
    }

    foreach ($processId in $pids) {
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "    Da dung PID $processId" -ForegroundColor Green
        } catch {
            Write-Host "    Khong dung duoc PID $processId : $_" -ForegroundColor Red
            return $false
        }
    }
    Start-Sleep -Seconds 2
    return $true
}

Write-Host ''
Write-Host '=============================================================' -ForegroundColor Cyan
Write-Host '  TRO LY SUC KHOE VINMEC - ReAct Agent + MCP + Giao dien Web' -ForegroundColor Cyan
Write-Host '=============================================================' -ForegroundColor Cyan
Write-Host ''

# --- Kiểm tra môi trường -----------------------------------------------------
if (-not (Test-Path $python)) {
    Write-Host '[X] Chua co moi truong ao .venv' -ForegroundColor Red
    Write-Host '    Chay: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
    exit 1
}

if (-not (Test-Path (Join-Path $root 'web\node_modules'))) {
    Write-Host '[X] Chua cai thu vien cho giao dien web' -ForegroundColor Red
    Write-Host '    Chay: cd web; npm install'
    exit 1
}

$env:PYTHONIOENCODING = 'utf-8'
if ($Mock) {
    $env:LLM_PROVIDER = 'mock'
    Write-Host '[i] Che do MOCK OFFLINE - khong goi API that, khong ton quota' -ForegroundColor Yellow
} else {
    Write-Host '[i] Che do LLM THAT - doc cau hinh tu file .env' -ForegroundColor Green
}

# --- Giai phong cong neu dang bi chiem ---------------------------------------
if (-not (Resolve-PortConflict -Port $ApiPort -Label 'Agent API')) { exit 1 }
if (-not (Resolve-PortConflict -Port $WebPort -Label 'Giao dien web')) { exit 1 }

# --- Khởi động API server ----------------------------------------------------
Write-Host ''
Write-Host "[1/2] Khoi dong Agent API tren cong $ApiPort ..." -ForegroundColor Cyan
$api = Start-Process -FilePath $python `
    -ArgumentList '-u', (Join-Path $root 'src\api_server.py'), '--port', $ApiPort `
    -WorkingDirectory $root -PassThru -NoNewWindow

Start-Sleep -Seconds 3

try {
    $health = Invoke-RestMethod "http://localhost:$ApiPort/api/health" -TimeoutSec 5
    Write-Host "      OK - Provider: $($health.provider) ($($health.model))" -ForegroundColor Green
    Write-Host "      MCP Server: $($health.mcp_server) | $($health.tools.Count) cong cu" -ForegroundColor Green
    if (-not $health.live_llm) {
        Write-Host '      [!] Dang chay Mock - dien GEMINI_API_KEY vao .env de dung LLM that' -ForegroundColor Yellow
    }
} catch {
    Write-Host '      [X] API khong phan hoi. Kiem tra lai log ben tren.' -ForegroundColor Red
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    exit 1
}

# --- Khởi động giao diện web -------------------------------------------------
Write-Host ''
Write-Host "[2/2] Khoi dong giao dien web tren cong $WebPort ..." -ForegroundColor Cyan
$env:AGENT_API_URL = "http://localhost:$ApiPort"
$web = Start-Process -FilePath 'npm.cmd' `
    -ArgumentList 'run', 'dev' `
    -WorkingDirectory (Join-Path $root 'web') -PassThru -NoNewWindow

Start-Sleep -Seconds 8

Write-Host ''
Write-Host '=============================================================' -ForegroundColor Green
Write-Host "  San sang! Mo trinh duyet tai: http://localhost:$WebPort" -ForegroundColor Green
Write-Host '=============================================================' -ForegroundColor Green
Write-Host ''
Write-Host '  Goi y demo:' -ForegroundColor White
Write-Host '   1. Chon ho so "Tran Thi Binh (BN2024002)" o thanh ben'
Write-Host '   2. Hoi: "Toi bi o chua tro lai, chon giup toi bac si phu hop va dat lich som nhat"'
Write-Host '   3. Xem Agent goi 3 cong cu lien tiep, giai thich vi sao chon bac si'
Write-Host '   4. Bam "Trace log" de xem chuoi Thought -> Action -> Observation'
Write-Host ''
Write-Host '  Nhan Ctrl+C de dung ca hai tien trinh.' -ForegroundColor Yellow
Write-Host ''

Start-Process "http://localhost:$WebPort"

try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($api.HasExited) { Write-Host '[!] API server da dung.' -ForegroundColor Red; break }
        if ($web.HasExited) { Write-Host '[!] Web server da dung.' -ForegroundColor Red; break }
    }
} finally {
    Write-Host ''
    Write-Host 'Dang dung cac tien trinh...' -ForegroundColor Yellow
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
    if ($web -and -not $web.HasExited) { Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue }
    Write-Host 'Da dung. Tam biet!' -ForegroundColor Green
}
