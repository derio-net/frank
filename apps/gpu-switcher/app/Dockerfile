# Build natively on host arch, cross-compile for amd64
# (avoids QEMU emulation crashes when building on arm64 Macs)
FROM golang:1.26-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o gpu-switcher .

FROM --platform=linux/amd64 gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /build/gpu-switcher /gpu-switcher
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/gpu-switcher"]
