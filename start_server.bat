@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   SQL Adaptive Training - Server Starter
echo ============================================
echo.

set "BACKEND_DIR=%~dp0backend"
set "CONFIG_FILE=%~dp0server_path.conf"
set "REQUIREMENTS=%BACKEND_DIR%\requirements.txt"

REM 默认安装版本（大版本号，会自动查找最新微版本）
set "PYTHON_MAJOR=3"
set "PYTHON_MINOR=13"
set "PYTHON_VER=%PYTHON_MAJOR%.%PYTHON_MINOR%"
set "DEFAULT_INSTALL_DIR=C:\Python%PYTHON_MAJOR%%PYTHON_MINOR%"

REM ============================================
REM  Step 1: 检查配置文件（设备管理者预设路径 + 版本）
REM  格式: 第1行=Python路径, 第2行=偏好版本(可选)
REM ============================================
if exist "%CONFIG_FILE%" (
    set "LINE_NUM=0"
    for /f "usebackq delims=" %%p in ("%CONFIG_FILE%") do (
        set /a LINE_NUM+=1
        if !LINE_NUM! EQU 1 (
            set "CUSTOM_PATH=%%p"
        )
        if !LINE_NUM! EQU 2 (
            set "CUSTOM_VER=%%p"
        )
    )
    REM 如果配置了自定义版本，覆盖默认
    if defined CUSTOM_VER (
        for /f "tokens=1,2 delims=." %%a in ("!CUSTOM_VER!") do (
            set "PYTHON_MINOR=%%b"
            set "PYTHON_VER=%%a.%%b"
            set "DEFAULT_INSTALL_DIR=C:\Python%%a%%b"
        )
        echo [INFO] 配置文件指定版本: Python !PYTHON_VER!
    )
    if defined CUSTOM_PATH (
        if exist "!CUSTOM_PATH!" (
            set "PYTHON_EXE=!CUSTOM_PATH!"
            echo [INFO] 使用自定义 Python 路径: !PYTHON_EXE!
            goto :check_python_works
        ) else (
            echo [WARN] 配置文件中的路径无效，将自动探测...
        )
    )
)

REM ============================================
REM  Step 2: 自动探测 Python（多策略 + 逐个验证）
REM  核心原则: 不只看"找到没"，还要"能跑通"——跳过 Store 存根/残留无效路径
REM ============================================
echo [INFO] 正在搜索 Python ...

REM 策略1: 系统 PATH 中的 python（逐个尝试验证）
for /f "delims=" %%p in ('where python 2^>nul') do call :try_python "%%p" && goto :check_python_works

REM 策略2: 系统 PATH 中的 python3
for /f "delims=" %%p in ('where python3 2^>nul') do call :try_python "%%p" && goto :check_python_works

REM 策略3: py 启动器
where py >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%p in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
        call :try_python "%%p" && goto :check_python_works
    )
)

REM 策略4: 遍历常见安装目录（版本无关，从高到低）
for %%b in ("%LOCALAPPDATA%\Programs\Python" "C:\" "C:\Program Files" "C:\Program Files (x86)") do (
    if exist "%%~b" (
        for /f "delims=" %%d in ('dir /b /ad "%%~b\Python3*" 2^>nul ^| sort /r') do (
            call :try_python "%%~b\%%d\python.exe" && goto :check_python_works
        )
    )
)

REM 策略5: 注册表查询（遍历所有 Python 3.x 版本，从高到低）
for %%h in (HKCU HKLM) do (
    for /f "delims=" %%k in ('reg query "%%h\Software\Python\PythonCore" 2^>nul ^| findstr "PythonCore\\3\." ^| sort /r') do (
        for /f "tokens=2*" %%a in ('reg query "%%k\InstallPath" /ve 2^>nul ^| findstr "REG_SZ"') do (
            call :try_python "%%b\python.exe" && goto :check_python_works
        )
    )
)

REM 全部策略失败 → 进入自动安装流程
goto :python_not_found

REM ============================================
REM  子程序: 验证一个 Python 候选路径是否真正可用
REM  %1 = 待验证的 python 路径
REM  返回: errorlevel 0 = 可用, 1 = 不可用（跳过）
REM ============================================
:try_python
set "CANDIDATE=%~1"
REM 过滤 Microsoft Store 存根（不能执行，只是跳转链接）
echo !CANDIDATE! | findstr /i "WindowsApps" >nul
if !ERRORLEVEL! EQU 0 exit /b 1
REM 文件必须实际存在
if not exist "!CANDIDATE!" exit /b 1
REM 真正执行 --version，验证不是壳/假货
"!CANDIDATE!" --version >nul 2>&1
if !ERRORLEVEL! NEQ 0 exit /b 1
REM 全部通过 → 这才是真正可用的 Python
set "PYTHON_EXE=!CANDIDATE!"
for /f "tokens=*" %%v in ('"!PYTHON_EXE!" --version 2^>^&1') do echo [INFO] 找到可用 Python: %%v  [ !PYTHON_EXE! ]
exit /b 0

REM ============================================
REM  未找到可用 Python → 自动安装
REM ============================================
:python_not_found

REM ============================================
REM  Step 3: 未找到 Python → 自动安装
REM ============================================
echo.
echo [WARN] 本机未检测到 Python 环境。
echo.
echo   默认安装版本: Python %PYTHON_VER%.x （自动匹配最新微版本）
echo   默认安装路径: %DEFAULT_INSTALL_DIR%
echo   （设备管理者可在 server_path.conf 中预设路径和版本）
echo.

set /p INSTALL_CHOICE="是否自动安装 Python %PYTHON_VER%.x ？(Y/N): "
if /i not "!INSTALL_CHOICE!"=="Y" (
    echo [ERROR] Python 是运行本系统必须的环境。请手动安装后重试。
    echo         下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

set /p INSTALL_DIR="请输入安装路径（直接回车使用默认 %DEFAULT_INSTALL_DIR% ）: "
if "!INSTALL_DIR!"=="" set "INSTALL_DIR=%DEFAULT_INSTALL_DIR%"

REM 去除路径末尾的引号和反斜杠
set "INSTALL_DIR=!INSTALL_DIR:"=!"
if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"

echo.
echo [INFO] 正在获取 Python %PYTHON_VER% 最新微版本...

REM 从 python.org FTP 自动匹配最新微版本（从高到低尝试）
set "DOWNLOAD_OK=0"
for %%m in (9 8 7 6 5 4 3 2 1 0) do (
    if "!DOWNLOAD_OK!"=="0" (
        set "TEST_VER=%PYTHON_VER%.%%m"
        set "TEST_URL=https://www.python.org/ftp/python/!TEST_VER!/python-!TEST_VER!-amd64.exe"
        echo [INFO] 尝试 !TEST_VER! ...
        curl -sI "!TEST_URL!" 2>nul | findstr "200 OK" >nul
        if !ERRORLEVEL! EQU 0 (
            set "PYTHON_FULL_VER=!TEST_VER!"
            set "DOWNLOAD_URL=!TEST_URL!"
            set "DOWNLOAD_OK=1"
        )
    )
)
REM 如果 FTP 探测失败，使用默认微版本 2 直接尝试下载
if "!DOWNLOAD_OK!"=="0" (
    set "PYTHON_FULL_VER=%PYTHON_VER%.2"
    set "DOWNLOAD_URL=https://www.python.org/ftp/python/!PYTHON_FULL_VER!/python-!PYTHON_FULL_VER!-amd64.exe"
    echo [WARN] 版本探测失败，尝试 !PYTHON_FULL_VER!
)

echo [INFO] 目标版本: Python !PYTHON_FULL_VER!
echo [INFO] 正在下载 Python !PYTHON_FULL_VER! ...
set "PYTHON_INSTALLER=%TEMP%\python-installer.exe"

REM 尝试 curl（Win10+ 内置）
curl -L -o "!PYTHON_INSTALLER!" "!DOWNLOAD_URL!" 2>nul
if !ERRORLEVEL! NEQ 0 (
    REM 回退: bitsadmin
    echo [INFO] curl 失败，尝试 bitsadmin ...
    bitsadmin /transfer "PythonDownload" "!DOWNLOAD_URL!" "!PYTHON_INSTALLER!" >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo [ERROR] 下载 Python 安装包失败，请检查网络连接或手动安装。
        echo         下载地址: https://www.python.org/downloads/
        del "!PYTHON_INSTALLER!" >nul 2>&1
        pause
        exit /b 1
    )
)

echo [INFO] 正在安装 Python 到 !INSTALL_DIR! （静默安装，请稍候...）
"!PYTHON_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_tcltk=0 TargetDir="!INSTALL_DIR!"
set "INSTALL_RESULT=!ERRORLEVEL!"
del "!PYTHON_INSTALLER!" >nul 2>&1

if !INSTALL_RESULT! NEQ 0 (
    echo [ERROR] Python 安装失败（错误码: !INSTALL_RESULT!）
    echo         请尝试以管理员身份运行或手动安装。
    pause
    exit /b 1
)

REM 等待安装完成并刷新环境
timeout /t 3 /nobreak >nul
set "PYTHON_EXE=!INSTALL_DIR!\python.exe"
if not exist "!PYTHON_EXE!" set "PYTHON_EXE=!INSTALL_DIR!\python3.exe"

echo [INFO] Python 安装完成: !PYTHON_EXE!
echo !PYTHON_EXE!>"%CONFIG_FILE%"
echo !PYTHON_FULL_VER!>>"%CONFIG_FILE%"
echo [INFO] 已将配置保存到 server_path.conf（路径 + 版本号）

goto :install_deps

REM ============================================
REM  Step 4: 确认 Python 可用（配置文件指定的路径做最终验证）
REM ============================================
:check_python_works
for /f "tokens=*" %%v in ('"!PYTHON_EXE!" --version 2^>^&1') do echo [INFO] 检测到: %%v

REM ============================================
REM  Step 5: 安装/更新依赖库
REM ============================================
:install_deps
echo.
echo [INFO] 检查依赖库...

REM 确保 pip 可用
"!PYTHON_EXE!" -m pip --version >nul
if !ERRORLEVEL! NEQ 0 (
    echo [WARN] pip 不可用，正在修复...
    "!PYTHON_EXE!" -m ensurepip --upgrade
    if !ERRORLEVEL! NEQ 0 (
        echo [ERROR] pip 修复失败，请检查 Python 安装。
        pause
        exit /b 1
    )
)

if exist "%REQUIREMENTS%" (
    echo [INFO] 正在安装依赖库（flask, flask-cors, requests, bs4, lxml）...
    "!PYTHON_EXE!" -m pip install -r "%REQUIREMENTS%" --quiet --disable-pip-version-check
    if !ERRORLEVEL! EQU 0 (
        echo [INFO] 依赖库安装完成。
    ) else (
        echo [WARN] 部分依赖库安装失败，尝试逐条安装...
        "!PYTHON_EXE!" -m pip install flask flask-cors requests beautifulsoup4 lxml --quiet --disable-pip-version-check
    )
) else (
    echo [WARN] 未找到 requirements.txt，跳过依赖检查。
)

REM ============================================
REM  Step 6: 启动服务
REM ============================================
if not exist "%BACKEND_DIR%\run.py" (
    echo [ERROR] 未找到 backend\run.py ！
    echo         请确保在项目根目录下运行本脚本。
    pause
    exit /b 1
)

echo.
echo ============================================
echo   启动服务...
echo   本地访问: http://localhost:5000
echo   按 Ctrl+C 停止服务
echo ============================================
echo.

REM 自动打开浏览器（非阻塞）
start "" http://localhost:5000

"!PYTHON_EXE!" "%BACKEND_DIR%\run.py"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ===== 启动失败！请检查上方错误信息 =====
    pause
    exit /b !ERRORLEVEL!
)

endlocal
