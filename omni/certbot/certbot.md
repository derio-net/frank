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
