# Stage 1: Build Hugo site
FROM ghcr.io/gohugoio/hugo:v0.157.0 AS builder
WORKDIR /src
COPY . .
RUN hugo --minify --baseURL https://blog.derio.net

# Stage 2: Serve with Caddy
FROM caddy:2.9-alpine
COPY --from=builder /src/public /usr/share/caddy
RUN printf ':8080 {\n    root * /usr/share/caddy\n    file_server\n    try_files {path} {path}/ /frank/index.html\n    header Cache-Control "public, max-age=3600"\n}\n' > /etc/caddy/Caddyfile
EXPOSE 8080
