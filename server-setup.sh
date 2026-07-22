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

has_pkg() {
  dpkg -s "$1" >/dev/null 2>&1
}

install_base_packages() {
  apt update
  apt install -y ca-certificates curl gnupg apache2-utils openssl
}

install_docker_repo() {
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME:-} stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null
}

docker_available() {
  command -v docker >/dev/null 2>&1 && docker --version >/dev/null 2>&1
}

compose_available() {
  docker compose version >/dev/null 2>&1
}

install_base_packages

# An existing Docker installation may come from Docker's repository, Ubuntu,
# Snap, or another source. Do not mix package sources or alter a working setup.
if docker_available; then
  echo "Existing Docker installation detected; leaving it unchanged."
  if ! compose_available; then
    echo "Docker is installed, but 'docker compose' is unavailable."
    echo "Refusing to modify the existing Docker installation automatically."
    echo "Install a Compose v2 plugin compatible with this Docker installation, then rerun."
    exit 1
  fi
else
  if command -v snap >/dev/null 2>&1 && snap list docker >/dev/null 2>&1; then
    echo "Snap Docker is installed but is not currently usable."
    echo "Refusing to install a second Docker distribution alongside it."
    exit 1
  fi

  echo "Installing Docker Engine and Compose v2 plugin..."
  install_docker_repo
  apt update
  apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

if command -v docker-compose >/dev/null 2>&1; then
  echo "Note: docker-compose (v1) detected. Prefer 'docker compose'."
fi

echo "Docker installed:"
docker --version
if compose_available; then
  docker compose version
else
  echo "Compose v2 plugin not available. Check docker-compose-plugin installation."
  exit 1
fi

install_netdata() {
  local installer
  local install_status

  if command -v netdata >/dev/null 2>&1 || has_pkg netdata; then
    echo "Netdata already installed."
    return
  fi

  echo "Installing Netdata Agent..."
  installer="$(mktemp /tmp/netdata-kickstart.XXXXXX.sh)"

  if ! curl -fL --retry 3 --retry-delay 2 \
    -o "$installer" https://get.netdata.cloud/kickstart.sh; then
    echo "Failed to download the Netdata installer."
    rm -f "$installer"
    return 1
  fi

  install_status=0
  DISABLE_TELEMETRY=1 bash "$installer" \
    --release-channel stable \
    --non-interactive || install_status=$?
  rm -f "$installer"

  if [ "$install_status" -ne 0 ]; then
    echo "Netdata installer failed with exit code $install_status."
    return "$install_status"
  fi
}

configure_netdata_auth() {
  local htpasswd_file="/etc/nginx/.htpasswd"
  local credential_file="/root/netdata-basic-auth.txt"
  local user="${NETDATA_AUTH_USER:-netdata}"
  local password="${NETDATA_AUTH_PASSWORD:-}"
  local generated_password="false"

  install -m 0755 -d /etc/nginx

  if [ -f "$htpasswd_file" ]; then
    echo "Netdata basic-auth file already exists at $htpasswd_file."
    return
  fi

  # Docker creates a directory at a missing bind-mount source path. This can
  # happen when the Nginx container starts before the htpasswd file exists.
  if [ -d "$htpasswd_file" ]; then
    if ! rmdir "$htpasswd_file"; then
      echo "$htpasswd_file is a non-empty directory; refusing to replace it."
      return 1
    fi
    echo "Removed the empty directory Docker created at $htpasswd_file."
  fi

  if [ -z "$password" ]; then
    password="$(openssl rand -base64 24)"
    generated_password="true"
  fi

  htpasswd -bc "$htpasswd_file" "$user" "$password"
  chmod 0644 "$htpasswd_file"

  if [ "$generated_password" = "true" ]; then
    umask 077
    {
      echo "Netdata basic-auth credentials"
      echo "username: $user"
      echo "password: $password"
    } > "$credential_file"
    echo "Generated Netdata basic-auth credentials at $credential_file."
    echo "Read them with: sudo cat $credential_file"
  fi
}

configure_netdata_docker_access() {
  if id netdata >/dev/null 2>&1 && getent group docker >/dev/null 2>&1; then
    if id -nG netdata | tr ' ' '\n' | grep -qx docker; then
      echo "Netdata already belongs to the Docker group."
      return
    fi

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

if [ "${CONFIGURE_UFW:-false}" = "true" ]; then
  apt install -y ufw
  configure_firewall
else
  echo "Leaving the existing firewall configuration unchanged."
  echo "Set CONFIGURE_UFW=true to configure and enable UFW."
fi

install_netdata
configure_netdata_auth
configure_netdata_docker_access

echo "Netdata installed. Access it through the app Nginx proxy at /netdata/ after deploying the updated compose and nginx config."
