#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/monkey-bot}"
SERVICE_FILE="${SERVICE_FILE:-monkey-bot.service}"
SWAP_FILE="${SWAP_FILE:-/swapfile}"
SWAP_SIZE="${SWAP_SIZE:-2G}"
START_SERVICE="${START_SERVICE:-true}"

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this script as the app user, not root." >&2
  exit 1
fi

if [ ! -f "$APP_DIR/requirements.txt" ]; then
  echo "requirements.txt not found in $APP_DIR" >&2
  exit 1
fi

if [ ! -f "$APP_DIR/$SERVICE_FILE" ]; then
  echo "$SERVICE_FILE not found in $APP_DIR" >&2
  exit 1
fi

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  fonts-noto-cjk \
  python3 \
  python3-pip \
  python3-venv

if [ ! -f "$SWAP_FILE" ] && [ "$(free -m | awk '/^Mem:/ {print $2}')" -lt 1800 ]; then
  sudo fallocate -l "$SWAP_SIZE" "$SWAP_FILE" || sudo dd if=/dev/zero of="$SWAP_FILE" bs=1M count=2048
  sudo chmod 600 "$SWAP_FILE"
  sudo mkswap "$SWAP_FILE"
  sudo swapon "$SWAP_FILE"
  if ! grep -q "^$SWAP_FILE " /etc/fstab; then
    echo "$SWAP_FILE none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
  fi
fi

cd "$APP_DIR"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m py_compile monkey_bot.py
python monkey_bot.py --check

sudo cp "$APP_DIR/$SERVICE_FILE" /etc/systemd/system/monkey-bot.service
sudo systemctl daemon-reload
sudo systemctl enable monkey-bot.service
if [ "$START_SERVICE" = "true" ]; then
  sudo systemctl restart monkey-bot.service
  sudo systemctl --no-pager --lines=20 status monkey-bot.service
else
  echo "Installed monkey-bot.service without starting it."
fi

