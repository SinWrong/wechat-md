@echo off
rem 用法：wechat_md.bat 文案.md [-o 输出.md] [--html 输出.html] [--theme news]
rem 也可以把文件直接拖到这个 bat 上
setlocal
if "%~1"=="" (
  echo 用法: wechat_md.bat 文案.md [-o 输出.md] [--html 输出.html]
  exit /b 1
)
python "%~dp0tools\wechat_md.py" %*
