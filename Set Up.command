#!/bin/bash
# Double-click to run. (asks a few questions and saves your settings)
cd "$(dirname "$0")" || exit 1
if [ ! -x venv/bin/python ]; then
  echo "This folder isn't installed yet. See 'Install' in README.md."
else
  ./venv/bin/python engine/setup_wizard.py
fi
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
