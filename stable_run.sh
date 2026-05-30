#!/bin/bash
cd "$(dirname "$0")"
PYTHONWARNINGS="ignore" python3 chat.py 2>/dev/null
