@echo off
rem 用法：wechat_md_gui.bat            直接打开编辑器
rem       wechat_md_gui.bat 文案.md    打开时载入这篇
setlocal
python "%~dp0tools\wechat_md_gui.py" %*
if errorlevel 1 pause
