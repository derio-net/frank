# Hugo uses the committed module pins and canonical URL in hugo.toml.
FROM ghcr.io/gohugoio/hugo:v0.157.0 AS builder
WORKDIR /src
COPY --chown=hugo:hugo . .
RUN hugo --minify --cleanDestinationDir

# The same post-render export used by scripts/build-site.py in CI.
FROM python:3.12-alpine AS exporter
WORKDIR /src
COPY --from=builder /src/public ./public
COPY scripts/export-content.py ./export-content.py
RUN python3 export-content.py public

FROM caddy:2.9-alpine
COPY --from=exporter /src/public /usr/share/caddy
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 8080
