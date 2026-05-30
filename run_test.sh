#!/bin/bash
# Run Capohm experimental mode (dev version)

cd "$(dirname "$0")"
PYTHONWARNINGS="ignore" python3 chat_dev.py 2> /dev/null
