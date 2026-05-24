FROM caddy:2.9-builder AS builder
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare \
    --with github.com/hslatman/caddy-crowdsec-bouncer/http \
    --with github.com/hslatman/caddy-crowdsec-bouncer/layer4

FROM caddy:2.9-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
