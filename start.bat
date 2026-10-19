@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8765"
set "BASE=http://%HOST%:%PORT%"
set "RC=0"
set "OPEN=1"
set "QUIET=0"
if /i "%~1"=="--no-open" (set "OPEN=0" & set "QUIET=1")
if /i "%~1"=="--quiet" (set "OPEN=0" & set "QUIET=1")

if not exist "logs" mkdir "logs"

set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 set "PY=py"
)
if not defined PY (
  echo [ERROR] 未找到 python，请先安装并加入 PATH
  set "RC=1"
  goto :finish
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('%HOST%', %PORT%); $c.Close(); exit 0 } catch { exit 1 }"
if not errorlevel 1 (
  echo [INFO] 服务已在运行: %BASE%
  set "RC=0"
  goto :finish
)

echo [INFO] 启动服务 %BASE%  (日志: logs\server.log)
start "Newspaper Reader" /min cmd /c "%PY% -m newspaper_reader --host %HOST% --port %PORT% >> logs\server.log 2>&1"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok = $false; for ($i = 0; $i -lt 40; $i++) { try { $r = Invoke-WebRequest -Uri '%BASE%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { $ok = $true; break } } catch {}; Start-Sleep -Milliseconds 500 }; if ($ok) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [ERROR] 启动失败，请查看 logs\server.log
  set "RC=1"
  goto :finish
)

echo [OK] 启动成功: %BASE%
if "%OPEN%"=="1" start "" "%BASE%"

:finish
if "%QUIET%"=="1" exit /b %RC%
echo.
pause
exit /b %RC%
