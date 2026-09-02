@echo off
chcp 65001 >nul
echo ====================================
echo   FlClash 断网一键修复工具
echo ====================================
echo.

echo [1/3] 正在关闭系统代理...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
echo       已关闭 (ProxyEnable = 0)

echo [2/3] 正在刷新系统 DNS 缓存...
ipconfig /flushdns >nul
echo       已刷新

echo [3/3] 正在通知系统设置已更改...
RUNDLL32.EXE wininet.dll,InternetSetOptionW 0,39,0,0
RUNDLL32.EXE wininet.dll,InternetSetOptionW 0,37,0,0
echo       已通知
echo.

echo ====================================
echo   修复完成! 请测试浏览器是否正常
echo ====================================
echo.
pause
