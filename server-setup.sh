#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Run as root: sudo ./server-setup.sh"
  exit 1
fi

if [ -f /etc/os-release ]; then
  . /etc/os-release
fi

if [ "${ID:-}" != "ubuntu" ]; then
  echo "Warning: this script is tested on Ubuntu."
fi

if command -v snap >/dev/null 2>&1 && snap list docker >/dev/null 2>&1; then
  echo "Snap Docker detected. Remove it to avoid conflicts:"
  echo "  sudo snap remove docker"
  exit 1
fi

has_pkg() {
  dpkg -s "$1" >/dev/null 2>&1
}

docker_source="none"
if has_pkg docker-ce || has_pkg docker-ce-cli; then
  docker_source="docker-ce"
elif has_pkg docker.io; then
  docker_source="docker-io"
fi

install_prereqs() {
  apt update
  apt install -y ca-certificates curl gnupg
}

install_docker_repo() {
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME:-} stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null
}

if [ "$docker_source" = "none" ]; then
  echo "Installing Docker Engine and Compose v2 plugin..."
  install_prereqs
  install_docker_repo
  apt update
  apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
  echo "Docker already installed ($docker_source). Installing Compose v2 plugin if needed..."
  apt update
  apt install -y docker-compose-plugin
fi

if command -v docker-compose >/dev/null 2>&1; then
  echo "Note: docker-compose (v1) detected. Prefer 'docker compose'."
fi

systemctl enable --now docker

echo "Docker installed:"
docker --version
if docker compose version >/dev/null 2>&1; then
  docker compose version
else
  echo "Compose v2 plugin not available. Check docker-compose-plugin installation."
  exit 1
fi
