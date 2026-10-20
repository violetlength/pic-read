@echo off
chcp 936 >nul
setlocal EnableExtensions
pushd "%~dp0" 2>nul
if errorlevel 1 goto :no_dir

set "HOST=127.0.0.1"
set "PORT=8765"
set "BASE=http://%HOST%:%PORT%"
set "LOGDIR=%CD%\logs"
set "LOG=%LOGDIR%\server.log"
set "RC=0"
set "OPEN=1"
set "QUIET=0"
set "CHECK=0"

:parse
if "%~1"=="" goto :parsed
set "KNOWN=0"
if /i "%~1"=="--quiet" (set "OPEN=0" & set "QUIET=1" & set "KNOWN=1")
if /i "%~1"=="--no-open" (set "OPEN=0" & set "QUIET=1" & set "KNOWN=1")
if /i "%~1"=="--check" (set "CHECK=1" & set "KNOWN=1")
if /i "%~1"=="-h" goto :usage
if /i "%~1"=="--help" goto :usage
if "%KNOWN%"=="0" (set "BADARG=%~1" & goto :bad_arg)
shift
goto :parse
:parsed

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>nul
if not exist "%LOGDIR%" goto :no_logdir

echo.
echo  图片文字阅读器 - 启动前检查
echo  ------------------------------------------------------------

rem ---------- 1. 找到可用的 Python（跳过 Microsoft Store 占位符）----------
set "PY="
for /f "delims=" %%P in ('where python 2^>nul ^| findstr /i /v "WindowsApps"') do if not defined PY set "PY=%%P"
if not defined PY for /f "delims=" %%P in ('where py 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY goto :no_python

%PY% -c "import sys" >nul 2>nul
if errorlevel 1 goto :py_broken

%PY% -c "import sys;print(sys.version.split()[0])" > "%TEMP%\np_pyver.txt" 2>nul
set "PYVER="
set /p PYVER=<"%TEMP%\np_pyver.txt"
%PY% -c "import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
if errorlevel 1 goto :old_python
echo  [OK] Python %PYVER%
echo       %PY%

rem ---------- 2. 依赖是否装齐 ----------
%PY% -c "import fastapi,uvicorn,multipart,aiofiles,PIL,numpy,cv2,reportlab,pytesseract,pydantic,pymupdf" 1>"%TEMP%\newspaper_reader_deps.txt" 2>&1
if errorlevel 1 goto :no_deps
echo  [OK] Python 依赖齐全

rem ---------- 3. 识别引擎（缺失不阻止启动，但转换会没有文字层）----------
set "TESS="
if defined TESSERACT_CMD if exist "%TESSERACT_CMD%" set "TESS=%TESSERACT_CMD%"
if not defined TESS if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESS for /f "delims=" %%P in ('where tesseract 2^>nul') do if not defined TESS set "TESS=%%P"
if not defined TESS goto :no_tess
echo  [OK] 识别引擎 %TESS%

rem ---------- 4. 端口状态 ----------
call :probe
if "%PROBE%"=="0" goto :start_server
if "%PROBE%"=="1" goto :already
goto :port_busy

:start_server
if "%CHECK%"=="1" goto :check_done
echo.
echo  [..] 正在启动 %BASE%   (日志: %LOG%)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a=@('-m','newspaper_reader','--host','%HOST%','--port','%PORT%'); $p=Start-Process -FilePath '%PY%' -ArgumentList $a -WindowStyle Hidden -PassThru -RedirectStandardOutput '%LOGDIR%\server.stdout' -RedirectStandardError '%LOG%'; for($i=0;$i -lt 40;$i++){ if($p.HasExited){ exit 2 }; $c=New-Object Net.Sockets.TcpClient; try{ $c.Connect('%HOST%',%PORT%); $c.Close(); exit 0 }catch{ try{$c.Close()}catch{} }; Start-Sleep -Milliseconds 500 }; exit 1"
set "WAITCODE=%errorlevel%"
if "%WAITCODE%"=="0" goto :start_ok
if "%WAITCODE%"=="2" goto :start_crashed
goto :start_timeout

:start_ok
echo  [OK] 启动成功: %BASE%
echo.
echo  浏览器地址: %BASE%
echo  停止服务:   双击 stop.bat
if "%OPEN%"=="1" start "" "%BASE%"
goto :done

:start_crashed
echo.
echo  [失败] 服务进程启动后立刻退出了（没有监听端口）。
goto :show_log

:start_timeout
echo.
echo  [失败] 服务 30 秒内没有响应。
goto :show_log

:show_log
echo  ------------------------------------------------------------
echo  %LOG% 的最后 20 行：
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path -LiteralPath '%LOG%') { Get-Content -LiteralPath '%LOG%' -Tail 20 }"
echo  ------------------------------------------------------------
echo  常见原因：依赖装到了另一个 Python 上、端口被占用、Tesseract 路径不对。
echo  把上面这段报错发出来即可定位问题。
set "RC=1"
goto :fail_end

:already
echo  [OK] 服务已在运行: %BASE%
if "%CHECK%"=="1" goto :check_done
if "%OPEN%"=="1" start "" "%BASE%"
goto :done

:check_done
echo.
echo  检查通过：环境满足要求，可以直接双击 start.bat 启动服务。
popd >nul
if "%QUIET%"=="1" exit /b 0
echo.
echo  按任意键关闭窗口...
pause >nul
exit /b 0

rem ================= 出错时停住窗口，不会闪退 =================

:no_python
echo.
echo  [失败] 没有找到 Python。
echo         1) 安装 Python 3.11 或更高版本（python.org 官方安装包）
echo         2) 安装时勾选 "Add python.exe to PATH"
echo         3) 关掉本窗口，重新双击 start.bat
set "RC=1"
goto :fail_end

:py_broken
echo.
echo  [失败] 找到了 Python 但无法运行: %PY%
echo         如果它是 Microsoft Store 的占位符，请到 python.org 重新安装官方版本。
set "RC=1"
goto :fail_end

:old_python
echo.
echo  [失败] Python 版本过低: %PYVER%（需要 3.11 或更高）
echo         请升级 Python 后重试。
set "RC=1"
goto :fail_end

:no_deps
echo.
echo  [失败] Python 依赖不完整，具体缺少的模块：
echo  ------------------------------------------------------------
type "%TEMP%\newspaper_reader_deps.txt"
echo  ------------------------------------------------------------
echo  解决办法：在本目录执行
echo      %PY% -m pip install -r requirements.txt
echo  装完重新双击 start.bat。
set "RC=1"
goto :fail_end

:no_tess
echo  [警告] 没有找到 Tesseract-OCR：服务能启动，但转换出的 PDF 没有可搜索文字层，
echo         界面徽标会显示「识别引擎未就绪」。
echo         安装 Tesseract-OCR（勾选中文简体语言包 chi_sim），默认路径
echo         C:\Program Files\Tesseract-OCR\tesseract.exe；或设置环境变量 TESSERACT_CMD。
echo  ------------------------------------------------------------
call :probe
if "%PROBE%"=="0" goto :start_server
if "%PROBE%"=="1" goto :already
goto :port_busy

:port_busy
echo.
echo  [失败] 端口 %PORT% 已被其它程序占用（占用者不是本程序）。
echo         请关闭占用 %PORT% 的程序，或改用其它端口启动：
echo             python -m newspaper_reader --port 9000
set "RC=1"
goto :fail_end

:no_dir
echo  [失败] 无法进入脚本所在目录: %~dp0
echo         请把整个文件夹放到本机磁盘（不要直接在压缩包或网络位置里运行）。
set "RC=1"
goto :fail_end

:no_logdir
echo  [失败] 无法创建 logs 目录（权限不足或磁盘只读）。
set "RC=1"
goto :fail_end

:bad_arg
echo  未知参数: %BADARG%
echo  用法见: start.bat --help
echo.
set "RC=1"
goto :fail_end

:usage
echo  用法: start.bat [--check^|--no-open^|--quiet]
echo     (无参数)   检查环境并启动服务，然后自动打开浏览器
echo     --check    只检查环境（Python / 依赖 / Tesseract / 端口），不启动
echo     --no-open  启动但不打开浏览器（不暂停）
echo     --quiet    同 --no-open，便于脚本调用
popd >nul
exit /b 0

:fail_end
echo.
if "%QUIET%"=="1" (popd >nul & exit /b %RC%)
echo  按任意键关闭窗口...
pause >nul
popd >nul
exit /b %RC%

:done
popd >nul
if "%QUIET%"=="1" exit /b 0
echo.
echo  按任意键关闭本窗口（服务会继续在后台运行）...
pause >nul
exit /b 0

rem ================= 子程序：0=端口空闲 1=本程序在跑 2=被其它程序占用 =================
:probe
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue); if ($l.Count -eq 0) { exit 0 }; foreach ($id in ($l.OwningProcess | Sort-Object -Unique)) { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $id) -ErrorAction SilentlyContinue; if ($p -and $p.CommandLine -and $p.CommandLine.Contains('newspaper_reader')) { exit 1 } }; exit 2"
set "PROBE=%errorlevel%"
exit /b 0
