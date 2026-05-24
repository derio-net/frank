FROM caddy:2.11.3-builder AS builder
# caddy-crowdsec-bouncer v0.10+ requires go 1.25.7 and caddy v2.10.2+.
# Bumping the builder image from 2.9 → 2.11.3 brings both. GOTOOLCHAIN=auto
# is still useful in case xcaddy resolves a transitive dep needing a
# newer go than the image ships.
ENV GOTOOLCHAIN=auto
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare \
    --with github.com/hslatman/caddy-crowdsec-bouncer/http \
    --with github.com/hslatman/caddy-crowdsec-bouncer/layer4

FROM caddy:2.11.3-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
