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

htpasswd_file="/etc/nginx/.htpasswd"
credential_file="/root/netdata-basic-auth.txt"
nginx_recreate_needed="false"

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

htpasswd_is_valid() {
  [ -f "$htpasswd_file" ] && [ -s "$htpasswd_file" ] &&
    awk -F: '
      NF >= 2 && length($1) > 0 && length($2) > 0 { found = 1 }
      END { exit(found ? 0 : 1) }
    ' "$htpasswd_file"
}

configure_netdata_auth() {
  local user="${NETDATA_AUTH_USER:-netdata}"
  local password="${NETDATA_AUTH_PASSWORD:-}"
  local generated_password="false"
  local create_file="false"

  install -m 0755 -d /etc/nginx

  if ! [[ "$user" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "Invalid NETDATA_AUTH_USER. Use letters, numbers, periods, underscores, or hyphens."
    return 1
  fi

  if [ -L "$htpasswd_file" ]; then
    echo "$htpasswd_file is a symbolic link; refusing to replace or follow it."
    return 1
  fi

  # Docker creates a directory at a missing bind-mount source path. This can
  # happen when the Nginx container starts before the htpasswd file exists.
  if [ -d "$htpasswd_file" ]; then
    if ! rmdir "$htpasswd_file"; then
      echo "$htpasswd_file is a non-empty directory; refusing to replace it."
      return 1
    fi
    echo "Removed the empty directory Docker created at $htpasswd_file."
    create_file="true"
  elif [ -e "$htpasswd_file" ] && [ ! -f "$htpasswd_file" ]; then
    echo "$htpasswd_file exists but is not a regular file; refusing to replace it."
    return 1
  elif [ -f "$htpasswd_file" ]; then
    if [ ! -s "$htpasswd_file" ]; then
      echo "The existing basic-auth file is empty; regenerating it."
      create_file="true"
    elif ! htpasswd_is_valid; then
      echo "$htpasswd_file is non-empty but contains no valid username:hash entry."
      echo "Refusing to overwrite an ambiguous authentication file."
      return 1
    elif [ -n "$password" ]; then
      printf '%s\n' "$password" | htpasswd -i "$htpasswd_file" "$user"
      echo "Updated basic-auth user '$user' without removing other users."
    else
      echo "Preserving the existing valid basic-auth file at $htpasswd_file."
    fi
  else
    create_file="true"
  fi

  if [ "$create_file" = "true" ]; then
    if [ -z "$password" ]; then
      password="$(openssl rand -base64 24)"
      generated_password="true"
    fi

    printf '%s\n' "$password" | htpasswd -ic "$htpasswd_file" "$user"
    echo "Created the Netdata basic-auth file at $htpasswd_file."
  fi

  chown root:root "$htpasswd_file"
  chmod 0644 "$htpasswd_file"

  if [ "$generated_password" = "true" ]; then
    umask 077
    {
      echo "Netdata basic-auth credentials"
      echo "username: $user"
      echo "password: $password"
    } > "$credential_file"
    chown root:root "$credential_file"
    chmod 0600 "$credential_file"
    echo "Generated Netdata basic-auth credentials at $credential_file."
    echo "Read them with: sudo cat $credential_file"
  elif [ -n "$password" ] && [ -f "$credential_file" ]; then
    echo "Note: $credential_file may contain credentials from an earlier generated password."
    echo "Explicitly supplied passwords are not written to that file."
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

ensure_netdata_running() {
  echo "Ensuring the Netdata service is enabled and running..."
  systemctl enable --now netdata

  if ! systemctl is-active --quiet netdata; then
    echo "Netdata is installed but the service is not active."
    systemctl status netdata --no-pager || true
    return 1
  fi

  if ! curl -fsS --max-time 5 \
    http://127.0.0.1:19999/api/v1/info >/dev/null; then
    echo "Netdata is active but its local API is not responding on port 19999."
    journalctl -u netdata -n 50 --no-pager || true
    return 1
  fi

  echo "Netdata is responding locally on port 19999."
}

configure_firewall() {
  echo "Configuring UFW firewall for SSH, HTTP, HTTPS, and private Netdata access..."
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow OpenSSH
  ufw allow 80/tcp
  ufw allow 443/tcp

  # Recreate the rules managed by this script so the private allow always
  # precedes the public deny, even if an earlier run was interrupted.
  ufw --force delete allow from 172.16.0.0/12 to any port 19999 proto tcp >/dev/null 2>&1 || true
  ufw --force delete allow 19999/tcp >/dev/null 2>&1 || true
  ufw --force delete deny 19999/tcp >/dev/null 2>&1 || true
  ufw allow from 172.16.0.0/12 to any port 19999 proto tcp
  ufw deny 19999/tcp
  ufw --force enable
}

security_passes=0
security_warnings=0
security_failures=0

security_pass() {
  security_passes=$((security_passes + 1))
  echo "PASS: $1"
}

security_warn() {
  security_warnings=$((security_warnings + 1))
  echo "WARN: $1"
}

security_fail() {
  security_failures=$((security_failures + 1))
  echo "FAIL: $1"
}

validate_firewall() {
  local status
  local numbered
  local allow_line
  local deny_line

  if [ "${CONFIGURE_UFW:-false}" != "true" ]; then
    security_warn "UFW validation skipped because CONFIGURE_UFW is not true."
    return
  fi

  status="$(ufw status verbose)"
  numbered="$(ufw status numbered)"

  if printf '%s\n' "$status" | grep -q '^Status: active$'; then
    security_pass "UFW is active."
  else
    security_fail "UFW is not active."
  fi

  if printf '%s\n' "$status" | grep -Eq 'OpenSSH[[:space:]]+ALLOW IN|22/tcp[[:space:]]+ALLOW IN'; then
    security_pass "SSH is allowed through UFW."
  else
    security_fail "No SSH allow rule was found in UFW."
  fi

  for port in 80 443; do
    if printf '%s\n' "$status" | grep -Eq "${port}/tcp[[:space:]]+ALLOW IN"; then
      security_pass "TCP port $port is allowed through UFW."
    else
      security_fail "No allow rule for TCP port $port was found in UFW."
    fi
  done

  allow_line="$(printf '%s\n' "$numbered" | grep -nE '19999/tcp[[:space:]]+ALLOW IN[[:space:]]+172\.16\.0\.0/12' | head -n 1 | cut -d: -f1 || true)"
  deny_line="$(printf '%s\n' "$numbered" | grep -nE '19999/tcp[[:space:]]+DENY IN[[:space:]]+Anywhere' | head -n 1 | cut -d: -f1 || true)"

  if [ -n "$allow_line" ] && [ -n "$deny_line" ] && [ "$allow_line" -lt "$deny_line" ]; then
    security_pass "Private Docker traffic to port 19999 is allowed before public traffic is denied."
  else
    security_fail "The ordered private-allow/public-deny rules for port 19999 were not found."
  fi
}

validate_nginx() {
  local container_id

  container_id="$(docker compose ps --status running -q nginx 2>/dev/null || true)"
  if [ -z "$container_id" ]; then
    security_warn "The Nginx container is not running; start it after setup to mount $htpasswd_file."
    return
  fi

  if docker compose exec -T nginx test -s /etc/nginx/.htpasswd >/dev/null 2>&1; then
    security_pass "The running Nginx container sees a non-empty htpasswd file."
  else
    nginx_recreate_needed="true"
    security_fail "The running Nginx container does not see a non-empty htpasswd file."
  fi

  if docker compose exec -T nginx \
    wget -qO- http://host.docker.internal:19999/api/v1/info >/dev/null 2>&1; then
    security_pass "The Nginx container can reach the Netdata API."
  else
    security_fail "The Nginx container cannot reach Netdata at host.docker.internal:19999."
  fi
}

validate_security_state() {
  local credential_mode
  local credential_owner

  echo
  echo "Validating Netdata security postconditions..."

  if systemctl is-enabled --quiet netdata; then
    security_pass "Netdata is enabled at boot."
  else
    security_fail "Netdata is not enabled at boot."
  fi

  if systemctl is-active --quiet netdata; then
    security_pass "Netdata is active."
  else
    security_fail "Netdata is not active."
  fi

  if curl -fsS --max-time 5 http://127.0.0.1:19999/api/v1/info >/dev/null; then
    security_pass "The local Netdata API is responding."
  else
    security_fail "The local Netdata API is not responding."
  fi

  if htpasswd_is_valid; then
    security_pass "$htpasswd_file is a non-empty regular file with a credential entry."
  else
    security_fail "$htpasswd_file is missing, empty, or malformed."
  fi

  if [ "$(stat -c '%U:%G' "$htpasswd_file" 2>/dev/null || true)" = "root:root" ] &&
    [ "$(stat -c '%a' "$htpasswd_file" 2>/dev/null || true)" = "644" ]; then
    security_pass "$htpasswd_file has root:root ownership and mode 0644."
  else
    security_fail "$htpasswd_file does not have the expected ownership or permissions."
  fi

  if [ -f "$credential_file" ]; then
    credential_mode="$(stat -c '%a' "$credential_file" 2>/dev/null || true)"
    credential_owner="$(stat -c '%U:%G' "$credential_file" 2>/dev/null || true)"
    if [ "$credential_mode" = "600" ] && [ "$credential_owner" = "root:root" ]; then
      security_pass "$credential_file is restricted to root."
    else
      security_fail "$credential_file exists but is not root:root with mode 0600."
    fi
  else
    security_warn "No generated credential file exists; this is expected when credentials were supplied explicitly."
  fi

  validate_firewall
  validate_nginx

  if [ "$nginx_recreate_needed" = "true" ]; then
    echo
    echo "ACTION REQUIRED: Recreate Nginx so it mounts the htpasswd file:"
    echo "  docker compose up -d --force-recreate nginx"
  fi

  echo
  echo "Security validation summary: $security_passes passed, $security_warnings warnings, $security_failures failed."
  echo "External check still required: confirm SERVER_PUBLIC_IP:19999 is unreachable from another machine."

  if [ "$security_failures" -ne 0 ]; then
    return 1
  fi
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
ensure_netdata_running
validate_security_state

echo "Netdata installed. Access it through the app Nginx proxy at /netdata/ after deploying the updated compose and nginx config."
