FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    qtbase5-dev \
    qtchooser \
    qt5-qmake \
    qtbase5-dev-tools \
    qttools5-dev-tools \
    libusb-1.0-0-dev \
    libhidapi-dev \
    pkgconf \
    libmbedtls-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch release_candidate_1.0rc2 \
    https://codeberg.org/OpenRGB/OpenRGB.git /src/OpenRGB

WORKDIR /src/OpenRGB

# Do not use `make install` — 1.0rc2 tries to write to /etc/systemd/system
RUN qmake OpenRGB.pro && make -j$(nproc)


FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    libhidapi-hidraw0 \
    libmbedtls14 \
    libqt5gui5 \
    libqt5widgets5 \
    libqt5network5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/OpenRGB/openrgb /usr/app/openrgb

# Required: Qt panics without a display unless told to use offscreen platform
ENV QT_QPA_PLATFORM=offscreen

ENTRYPOINT ["/usr/app/openrgb"]
