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

install_base_packages() {
  apt update
  apt install -y ca-certificates curl gnupg apache2-utils openssl ufw
}

docker_source="none"
if has_pkg docker-ce || has_pkg docker-ce-cli; then
  docker_source="docker-ce"
elif has_pkg docker.io; then
  docker_source="docker-io"
fi

install_prereqs() {
  install_base_packages
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
  install_base_packages
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

install_netdata() {
  if command -v netdata >/dev/null 2>&1; then
    echo "Netdata already installed."
    return
  fi

  echo "Installing Netdata Agent..."
  bash <(curl -Ss https://my-netdata.io/kickstart.sh) --stable-channel --disable-telemetry --dont-wait
}

configure_netdata_auth() {
  local htpasswd_file="/etc/nginx/.htpasswd"
  local credential_file="/root/netdata-basic-auth.txt"
  local user="${NETDATA_AUTH_USER:-netdata}"
  local password="${NETDATA_AUTH_PASSWORD:-}"

  install -m 0755 -d /etc/nginx

  if [ -f "$htpasswd_file" ]; then
    echo "Netdata basic-auth file already exists at $htpasswd_file."
    return
  fi

  if [ -z "$password" ]; then
    password="$(openssl rand -base64 24)"
    umask 077
    {
      echo "Netdata basic-auth credentials"
      echo "username: $user"
      echo "password: $password"
    } > "$credential_file"
    echo "Generated Netdata basic-auth credentials at $credential_file."
  fi

  htpasswd -bc "$htpasswd_file" "$user" "$password"
  chmod 0644 "$htpasswd_file"
}

configure_netdata_docker_access() {
  if id netdata >/dev/null 2>&1 && getent group docker >/dev/null 2>&1; then
    usermod -aG docker netdata
    systemctl restart netdata || true
    echo "Granted Netdata access to Docker metrics through the docker group."
  else
    echo "Skipping Netdata Docker group configuration; netdata user or docker group not found."
  fi
}

configure_firewall() {
  echo "Configuring UFW firewall for SSH, HTTP, HTTPS, and private Netdata access..."
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow OpenSSH
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw allow from 172.16.0.0/12 to any port 19999 proto tcp
  ufw deny 19999/tcp
  ufw --force enable
}

install_netdata
configure_netdata_auth
configure_netdata_docker_access
configure_firewall

echo "Netdata installed. Access it through the app Nginx proxy at /netdata/ after deploying the updated compose and nginx config."
