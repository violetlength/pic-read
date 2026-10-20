@echo off
chcp 936 >nul
setlocal EnableExtensions
pushd "%~dp0" 2>nul

set "PORT=8765"
set "RC=0"
set "QUIET=0"
set "FORCE=0"

:parse
if "%~1"=="" goto :run
set "KNOWN=0"
if /i "%~1"=="--quiet" (set "QUIET=1" & set "KNOWN=1")
if /i "%~1"=="--force" (set "FORCE=1" & set "KNOWN=1")
if /i "%~1"=="-h" goto :usage
if /i "%~1"=="--help" goto :usage
if "%KNOWN%"=="0" (set "BADARG=%~1" & goto :bad_arg)
shift
goto :parse

:run
call :kill own
if "%KRC%"=="0" goto :not_running
if "%KRC%"=="1" goto :stopped
if "%KRC%"=="2" goto :foreign
goto :still_running

:foreign
if "%FORCE%"=="1" goto :force
echo.
echo  [失败] 端口 %PORT% 被其它程序占用，占用者不是本服务，未做任何操作。
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue } | Sort-Object Id -Unique | Select-Object Id, ProcessName | Format-Table -AutoSize"
echo         如确认要强制结束这些程序: stop.bat --force
set "RC=1"
goto :end

:force
echo  [警告] 正在强制结束占用端口 %PORT% 的其它程序…
call :kill all
if "%KRC%"=="0" goto :not_running
if "%KRC%"=="1" goto :stopped
goto :still_running

:not_running
echo  [信息] 没有正在运行的服务（端口 %PORT% 空闲）。
set "RC=0"
goto :end

:stopped
echo  [OK] 服务已停止，端口 %PORT% 已释放。
set "RC=0"
goto :end

:still_running
echo.
echo  [失败] 停止失败，端口 %PORT% 仍被占用。
echo         可在任务管理器中结束相关 python 进程，或重启电脑后再试。
set "RC=1"
goto :end

:bad_arg
echo  未知参数: %BADARG%
echo  用法见: stop.bat --help
set "RC=1"
goto :end

:usage
echo  用法: stop.bat [--quiet^|--force]
echo     (无参数)  停止本程序的服务；端口被其它程序占用时不执行任何操作
echo     --quiet   不暂停，直接用返回码表示结果
echo     --force   强制结束占用端口 %PORT% 的程序（有风险，确认后使用）
popd >nul
exit /b 0

:end
popd >nul
if "%QUIET%"=="1" exit /b %RC%
echo.
echo  按任意键关闭窗口...
pause >nul
exit /b %RC%

rem ============ 子程序：mode=own 只停本程序；mode=all 停所有占用者 ============
rem KRC: 0=端口空闲 1=已停止 2=被其它程序占用（own 模式） 3=停止失败
:kill
powershell -NoProfile -ExecutionPolicy Bypass -Command "$mode='%~1'; $l=@(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue); if($l.Count -eq 0){exit 0}; $ids=@($l.OwningProcess | Sort-Object -Unique); $ours=@(); foreach($id in $ids){ $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$id) -ErrorAction SilentlyContinue; if($p -and $p.CommandLine -and $p.CommandLine.Contains('newspaper_reader')){ $ours += $id } }; if($mode -ne 'all' -and $ours.Count -eq 0){exit 2}; $target = $ids; if($mode -ne 'all'){ $target = $ours }; foreach($id in $target){ Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 900; if(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue){exit 3}; exit 1"
set "KRC=%errorlevel%"
exit /b 0
