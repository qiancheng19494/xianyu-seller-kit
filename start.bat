@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python app.py
) else (
    echo.
    echo 未检测到 Python。请先安装 Python 3.10 或更高版本，
    echo 安装时务必勾选 "Add Python to PATH"。
    echo 下载地址：https://www.python.org/downloads/
    echo.
    pause
)
