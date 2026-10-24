@echo off
chcp 65001 >nul
title 贪吃蛇 - Terminal Snake
cd /d "%~dp0"

rem 给游戏准备一个足够大的窗口（Windows Terminal 等环境可能无效，忽略即可）
mode con: cols=110 lines=32 >nul 2>nul

:MENU
cls
echo ============================================================
echo   终端贪吃蛇  Terminal Snake
echo ============================================================
echo.
echo   请选择启动模式：
echo.
echo     [1] 简单 (easy)          [2] 普通 (normal)      [3] 困难 (hard)
echo     [4] 穿墙模式 (wrap)      [5] 纯ASCII 无颜色     [6] AI演示 (demo)
echo     [7] 后台跑分 (headless)  [8] 运行自测 (selftest) [9] 退出
echo.
set /p CHOICE=请输入选项 [1-9]: 

if "%CHOICE%"=="1" set PARAMS=--difficulty easy
if "%CHOICE%"=="2" set PARAMS=--difficulty normal
if "%CHOICE%"=="3" set PARAMS=--difficulty hard
if "%CHOICE%"=="4" set PARAMS=--wrap --difficulty hard
if "%CHOICE%"=="5" set PARAMS=--ascii --no-color --difficulty normal
if "%CHOICE%"=="6" set PARAMS=--demo 200 --speed 20 --difficulty normal --wrap
if "%CHOICE%"=="7" set PARAMS=--headless 400 --difficulty hard --seed 42
if "%CHOICE%"=="8" set PARAMS=--selftest
if "%CHOICE%"=="9" (
    echo 再见！
    exit /b
)

if defined PARAMS (
    echo.
    echo 正在启动：python snake.py %PARAMS%
    echo ------------------------------------------------------------
    python snake.py %PARAMS%
    if errorlevel 1 (
        echo.
        echo ------------------------------------------------------------
        echo 游戏未能正常启动（错误码 %errorlevel%）。
        echo   * 请确认已安装 Python 3.7 或更高版本：
        echo       https://www.python.org/downloads/
        echo   * 如果提示终端窗口太小，请把窗口拉大后重新运行本脚本。
        echo   * 请在真实终端中运行（cmd / PowerShell / Git Bash / VS Code 终端）。
        echo ------------------------------------------------------------
        pause
        exit /b
    )

    echo.
    echo 游戏已结束，感谢游玩！
    pause
    goto MENU
) else (
    echo 无效选项，请重新输入。
    pause
    goto MENU
)
