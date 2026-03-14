# Build natively on host arch, cross-compile for target platform
# (avoids QEMU emulation crashes when building on arm64 Macs)
ARG TARGETPLATFORM=linux/amd64
ARG TARGETOS=linux
ARG TARGETARCH=amd64

FROM golang:1.26-alpine AS builder
ARG TARGETOS
ARG TARGETARCH
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -ldflags="-s -w" -o gpu-switcher .

FROM --platform=${TARGETPLATFORM} gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /build/gpu-switcher /gpu-switcher
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/gpu-switcher"]
