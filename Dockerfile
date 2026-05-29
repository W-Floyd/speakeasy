# syntax=docker/dockerfile:1

# ── Firmware ─────────────────────────────────────────────────────────────────
FROM ghcr.io/esphome/esphome:latest AS firmware

RUN arch=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/;s/armv7l/arm/') && \
    curl -fsSL "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_${arch}" \
    -o /usr/local/bin/yq && chmod +x /usr/local/bin/yq && \
    curl -fsSL "https://raw.githubusercontent.com/esphome/build-action/refs/heads/main/entrypoint.py" \
    -o /usr/local/lib/esphome-entrypoint.py

WORKDIR /config
COPY common/ common/
COPY speakeasy-*.yaml ./
COPY scripts/build-firmware.sh scripts/

RUN --mount=type=cache,target=/root/.platformio \
    --mount=type=cache,target=/config/.esphome \
    ./scripts/build-firmware.sh /output

# ── Web page ──────────────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS web

WORKDIR /src
COPY go.mod ./
COPY cmd/ cmd/
RUN --mount=type=cache,target=/root/.cache/go-build \
    go build -o /gen-index ./cmd/gen-index

COPY --from=firmware /output /output
RUN /gen-index -dir /output -out /output/index.html

# ── Server ────────────────────────────────────────────────────────────────────
FROM caddy:alpine

COPY --from=web /output /srv
COPY Caddyfile /etc/caddy/Caddyfile
