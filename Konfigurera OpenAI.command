#!/bin/zsh
cd -- "${0:A:h}"
.venv/bin/python tools/configure_openai.py
printf '\nTryck Retur för att stänga.\n'
read
