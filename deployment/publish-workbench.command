#!/bin/zsh
set -u
cd "${0:A:h}"
if /usr/bin/python3 activate_public.py; then
  print '公网发布验收完成。'
else
  print '尚未完成公网发布；本机工作台继续可用。请查看上方具体原因。'
fi
read '?按回车关闭窗口…'
