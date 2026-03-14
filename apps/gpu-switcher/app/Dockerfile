FROM golang:1.22-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o gpu-switcher .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /build/gpu-switcher /gpu-switcher
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/gpu-switcher"]
