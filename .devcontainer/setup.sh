#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
printf '%s\n' '[1/4] Checking the preinstalled C++ compiler...'
command -v c++ >/dev/null || { printf '%s\n' 'The playground image must provide a C++ compiler.' >&2; exit 1; }
printf '%s\n' '[2/4] Creating the isolated Python environment...'
python -m venv .playground/venv
printf '%s\n' '[3/4] Installing GITS dependencies and CMake...'
.playground/venv/bin/python -m pip install -r playground/requirements.txt
.playground/venv/bin/cmake --version
printf '%s\n' '[4/4] Preparing the gis launcher and example project...'
.playground/venv/bin/python playground/bootstrap.py
test -x .playground/bin/gis
printf '%s\n' 'GITS Playground ready! First: cmake -S . -B build && cmake --build build'
printf '%s\n' 'The initial missing demo_math.hpp error is expected. Follow playground/README.md.'
