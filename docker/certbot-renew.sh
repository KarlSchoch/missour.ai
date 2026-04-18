#!/bin/sh
set -eu

trap exit TERM

reload_signal_file="/var/www/certbot/.certbot-renewed"

while :; do
  certbot renew \
    --webroot -w /var/www/certbot \
    --deploy-hook "date -u +%Y-%m-%dT%H:%M:%SZ > ${reload_signal_file}"
  sleep 12h & wait "${!}"
done
