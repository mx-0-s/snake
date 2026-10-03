@echo off
chcp 65001 >nul
title 贪吃蛇 - Terminal Snake
cd /d "%~dp0"

rem 给游戏准备一个足够大的窗口（Windows Terminal 等环境可能无效，忽略即可）
mode con: cols=110 lines=32 >nul 2>nul

echo ============================================================
echo   终端贪吃蛇  Terminal Snake
echo ============================================================
echo.
echo   方向键 / WASD 转向     空格 暂停/继续
echo   R 重新开始             T 切换穿墙模式
echo   +/- 调速               Q 或 Esc 退出
echo.
echo   难度可通过参数指定，例如：
echo       python snake.py --difficulty hard --wrap
echo.
echo 正在启动……
echo.

python snake.py
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
