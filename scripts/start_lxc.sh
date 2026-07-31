#!/usr/bin/env bash
# Lance qbittorrent-nox + rgpy dans un conteneur LXC (Debian/Ubuntu),
# en installant les dependances manquantes au demarrage.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/var/log/ratiomaster"
RGPY_PORT="${RGPY_PORT:-3773}"
RGPY_WEBUI_PORT="${RGPY_WEBUI_PORT:-8088}"

mkdir -p "$LOG_DIR"

install_if_missing() {
    local bin="$1"
    local pkg="$2"
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "[start_lxc] $bin introuvable, installation de $pkg..."
        apt-get update -qq
        apt-get install -y "$pkg"
    fi
}

install_if_missing python3 python3
install_if_missing qbittorrent-nox qbittorrent-nox

cd "$REPO_DIR"

if ! pgrep -x qbittorrent-nox >/dev/null 2>&1; then
    echo "[start_lxc] demarrage de qbittorrent-nox"
    nohup qbittorrent-nox >"$LOG_DIR/qbittorrent-nox.log" 2>&1 &
else
    echo "[start_lxc] qbittorrent-nox deja actif"
fi

if ! pgrep -f "rgpy.webui" >/dev/null 2>&1; then
    echo "[start_lxc] demarrage de rgpy.webui (port $RGPY_PORT, webui $RGPY_WEBUI_PORT)"
    nohup python3 -m rgpy.webui --port "$RGPY_PORT" --webui-port "$RGPY_WEBUI_PORT" --verbose \
        >"$LOG_DIR/rgpy.log" 2>&1 &
else
    echo "[start_lxc] rgpy.webui deja actif"
fi

echo "[start_lxc] pret. Logs dans $LOG_DIR"
