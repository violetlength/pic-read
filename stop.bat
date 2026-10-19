@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "HOST=127.0.0.1"
set "PORT=8765"
set "RC=0"
set "QUIET=0"
if not "%~1"=="" set "QUIET=1"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$l = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if (-not $l) { Write-Output 'no listener'; exit 0 }; $ids = @($l.OwningProcess | Sort-Object -Unique); foreach ($p in $ids) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 800; if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { Write-Output ('still running: ' + ($ids -join ',')); exit 1 } else { Write-Output ('stopped pid: ' + ($ids -join ',')); exit 0 }"
if errorlevel 1 (
  echo [ERROR] 停止失败，请手动结束监听 %PORT% 端口的进程
  set "RC=1"
  goto :finish
)
echo [OK] 服务已停止
set "RC=0"

:finish
if "%QUIET%"=="1" exit /b %RC%
echo.
pause
exit /b %RC%
