#!/bin/bash
# Portable host setup only. Never touches a serial port or camera.
set -euo pipefail

task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$task_root"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This bootstrap is for macOS. Offline Python tests are also portable."
  exit 1
fi

python_command=""
for candidate in python3.11 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import ssl,sys; sys.exit(not (sys.version_info[:2] == (3,11) and ssl.OPENSSL_VERSION.startswith("OpenSSL")))' >/dev/null 2>&1; then
    python_command="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$python_command" ]]; then
  echo "Install the tested Python 3.11 with OpenSSL, then rerun this script."
  echo "With Homebrew already installed: brew install python@3.11"
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  "$python_command" -m venv .venv
fi
if ! .venv/bin/python -c 'import ssl,sys; sys.exit(not (sys.version_info[:2] == (3,11) and ssl.OPENSSL_VERSION.startswith("OpenSSL")))'; then
  echo "The existing .venv is not a usable Python 3.11/OpenSSL environment."
  echo "Move it aside and rerun; virtual environments must be created on this Mac."
  exit 1
fi

.venv/bin/python -m pip install -r requirements-dev.txt -e .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python -m sparkbench doctor

if ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "Camera helper compilation needs Apple Command Line Tools: xcode-select --install"
fi
echo "Host setup complete. Follow docs/archive/HANDOVER.txt to authorize and select the iPhone."
echo "No firmware was uploaded, no serial command was sent, and no camera was opened."
