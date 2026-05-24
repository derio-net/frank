FROM caddy:2.9-builder AS builder
# caddy-crowdsec-bouncer v0.10+ requires go 1.25.7; the caddy:2.9-builder
# image ships go 1.23. Setting GOTOOLCHAIN=auto lets Go bootstrap the
# required toolchain on demand.
ENV GOTOOLCHAIN=auto
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare \
    --with github.com/hslatman/caddy-crowdsec-bouncer/http \
    --with github.com/hslatman/caddy-crowdsec-bouncer/layer4

FROM caddy:2.9-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
