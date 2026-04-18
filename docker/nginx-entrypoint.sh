#!/bin/sh
set -eu

reload_signal_file="/var/www/certbot/.certbot-renewed"
last_signal=""

if [ -f "${reload_signal_file}" ]; then
  last_signal="$(cat "${reload_signal_file}" 2>/dev/null || true)"
fi

watch_for_cert_renewal() {
  while :; do
    if [ -f "${reload_signal_file}" ]; then
      current_signal="$(cat "${reload_signal_file}" 2>/dev/null || true)"
      if [ -n "${current_signal}" ] && [ "${current_signal}" != "${last_signal}" ]; then
        if nginx -t && nginx -s reload; then
          last_signal="${current_signal}"
        fi
      fi
    fi
    sleep 60
  done
}

watch_for_cert_renewal &
exec nginx -g "daemon off;"
