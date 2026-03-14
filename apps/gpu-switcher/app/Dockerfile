# Two-stage build: compile natively on host arch, package into amd64 runtime
# Stage 1: Build on host architecture (avoids QEMU emulation crashes on arm64 Macs)
FROM golang:1.26-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o gpu-switcher .

# Stage 2: Runtime — must be linux/amd64 for cluster nodes
FROM --platform=linux/amd64 gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /build/gpu-switcher /gpu-switcher
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/gpu-switcher"]
