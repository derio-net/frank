# Certbot

## Install certbot

```bash
sudo snap install --classic certbot
```

## Allow for root access

```bash
sudo snap set certbot trust-plugin-with-root=ok
```

## Install DNS provider

```bash
snap install certbot-dns-cloudflare
```

## Create creds file with API tokens

```bash
echo 'Cloudflare API token - check Cloudflare tokens in Bitwarden' > creds.ini
```

## Create certs for desired domain

```bash
cd /opt/manual_install/certbot && mkdir -p certbot/{config,work,logs}
certbot certonly --dns-cloudflare --config-dir config --work-dir work --logs-dir logs -d omni.frank.derio.net
```

## Renew certs

> ⚠️ The cert lives under `/opt/manual_install/certbot/`, **not** `/etc/letsencrypt/`. The snap-installed `snap.certbot.renew.timer` only scans `/etc/letsencrypt/` and is therefore a no-op for this cert. Renewals must use the same `--config-dir` / `--work-dir` / `--logs-dir` flags as the initial `certonly`.

### Manual renew

```bash
sudo /snap/bin/certbot renew \
  --config-dir /opt/manual_install/certbot/config \
  --work-dir   /opt/manual_install/certbot/work \
  --logs-dir   /opt/manual_install/certbot/logs \
  --deploy-hook 'docker restart omni'
```

The `--deploy-hook` runs only when certbot actually issues a new cert (i.e. inside the 30-day pre-expiry window), so it's safe to invoke daily. The hook is persisted into the renewal config after the first run with this flag.

If certbot complains `Another instance of Certbot is already running`, first verify nothing is actually running and then remove the stale lockfiles:

```bash
pgrep -af certbot                                                 # must return empty
sudo rm -f /opt/manual_install/certbot/{config,work,logs}/.certbot.lock
```

### Automated renew (systemd timer)

The default snap timer doesn't cover this cert. Install a dedicated unit:

```bash
sudo tee /usr/local/sbin/omni-cert-renew.sh > /dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
/snap/bin/certbot renew \
  --config-dir /opt/manual_install/certbot/config \
  --work-dir   /opt/manual_install/certbot/work \
  --logs-dir   /opt/manual_install/certbot/logs \
  --deploy-hook 'docker restart omni' \
  --quiet
EOF
sudo chmod 755 /usr/local/sbin/omni-cert-renew.sh

sudo tee /etc/systemd/system/omni-cert-renew.service > /dev/null <<'EOF'
[Unit]
Description=Renew Let's Encrypt cert for omni.frank.derio.net and reload Omni container
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/omni-cert-renew.sh
EOF

sudo tee /etc/systemd/system/omni-cert-renew.timer > /dev/null <<'EOF'
[Unit]
Description=Daily timer for omni cert renewal

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true
Unit=omni-cert-renew.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now omni-cert-renew.timer
systemctl list-timers omni-cert-renew.timer
```

### Verify

```bash
# On omni Pi:
echo | openssl s_client -connect localhost:8100 -servername omni.frank.derio.net 2>/dev/null \
  | openssl x509 -noout -dates

# From any client (must return 200 / 200 / 401):
curl -sSk -o /dev/null -w "root=%{http_code}\n" https://omni.frank.derio.net/
curl -sSk -o /dev/null -w "oidc=%{http_code}\n" https://omni.frank.derio.net/.well-known/openid-configuration
curl -sSk -o /dev/null -w "api =%{http_code}\n" https://omni.frank.derio.net:8100/.well-known/openid-configuration
```
