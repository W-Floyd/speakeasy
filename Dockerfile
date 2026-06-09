# syntax=docker/dockerfile:1
# Generated from speakeasy-*.yaml — do not edit directly.
# Run: go run ./cmd/gen-ci

# ── Setup ─────────────────────────────────────────────────────────────────────
FROM ghcr.io/esphome/esphome:latest AS base

RUN arch=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/;s/armv7l/arm/') && \
    curl -fsSL "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_${arch}" \
    -o /usr/local/bin/yq && chmod +x /usr/local/bin/yq && \
    curl -fsSL "https://raw.githubusercontent.com/esphome/build-action/refs/heads/main/entrypoint.py" \
    -o /usr/local/lib/esphome-entrypoint.py && \
    apt-get update -qq && apt-get install -y --no-install-recommends ccache

WORKDIR /config
COPY common/ common/
COPY primer.yaml ./

# ── Primed: downloads ESP-IDF toolchain independently of variant config changes ─
FROM base AS primed
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-primer \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest primer.yaml

# ── Variants base: variant yamls copied after toolchain is primed ─────────────
FROM primed AS variants
COPY speakeasy-*.yaml ./

# ── speakeasy-ss
FROM variants AS esphome-ss
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss && \
    cp -r "${build_dir}/." /output/speakeasy-ss/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc
FROM esphome-ss AS esphome-sc
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc && \
    cp -r "${build_dir}/." /output/speakeasy-sc/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt
FROM esphome-sc AS esphome-ss-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt
FROM esphome-ss-bt AS esphome-sc-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt/ && \
    rm -rf "${build_dir}"

# ── Snapclient base ──────────────────────────────────────────────────────────
FROM espressif/idf:v5.5.4 AS snapclient-base

SHELL ["/bin/bash", "-c"]
WORKDIR /snapclient
COPY snapclient/ .
COPY snapclient-kconfig/ /snapclient-kconfig/

# ── snapclient-mdns
FROM snapclient-base AS snapclient-mdns
RUN source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.mdns" \
      -B build-mdns \
      build && \
    idf.py -B build-mdns merge-bin && \
    mkdir -p /output/snapclient-mdns && \
    python3 ${IDF_PATH}/tools/idf_size.py --format json build-mdns/snapclient.map > /output/snapclient-mdns/size.json && \
    cp build-mdns/merged-binary.bin /output/snapclient-mdns/merged.bin && \
    cp build-mdns/snapclient.bin /output/snapclient-mdns/snapclient-mdns-ota.bin && \
    printf '{"name":"Snapclient mdns","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-mdns/manifest.json && \
    _ota=/output/snapclient-mdns/snapclient-mdns-ota.bin && \
    file_sha=$(sha256sum "${_ota}" | cut -d' ' -f1) && \
    sc_sha=$(python3 -c "import struct,sys;d=open('${_ota}','rb').read();i=next(i for i in range(0,len(d)-176,4)if struct.unpack_from('<I',d,i)[0]==0xABCD5432);print(d[i+144:i+176].hex(),end='')") && \
    sc_ver=${sc_sha:0:8} && \
    pages_base="https://w-floyd.github.io/speakeasy" && \
    printf '{"version":"%s","url":"%s/snapclient-mdns/snapclient-mdns-ota.bin","sha256":"%s","file_sha256":"%s","release_notes":"snapclient@%s"}' \
      "${sc_ver}" "${pages_base}" "${sc_sha}" "${file_sha}" "${sc_ver}" \
      > /output/snapclient-mdns/ota-manifest.json

# ── snapclient-mdns-nopull
FROM snapclient-base AS snapclient-mdns-nopull
RUN source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.mdns-nopull" \
      -B build-mdns-nopull \
      build && \
    idf.py -B build-mdns-nopull merge-bin && \
    mkdir -p /output/snapclient-mdns-nopull && \
    python3 ${IDF_PATH}/tools/idf_size.py --format json build-mdns-nopull/snapclient.map > /output/snapclient-mdns-nopull/size.json && \
    cp build-mdns-nopull/merged-binary.bin /output/snapclient-mdns-nopull/merged.bin && \
    cp build-mdns-nopull/snapclient.bin /output/snapclient-mdns-nopull/snapclient-mdns-nopull-ota.bin && \
    printf '{"name":"Snapclient mdns nopull","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-mdns-nopull/manifest.json

# ── Collect ──────────────────────────────────────────────────────────────────
FROM alpine AS collect
COPY --from=esphome-sc-bt /output /output
COPY --from=snapclient-mdns /output/snapclient-mdns /output/snapclient-mdns
COPY --from=snapclient-mdns-nopull /output/snapclient-mdns-nopull /output/snapclient-mdns-nopull

# ── Web page ──────────────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS web

WORKDIR /src
COPY go.mod ./
COPY cmd/ cmd/
RUN --mount=type=cache,target=/root/.cache/go-build \
    go build -o /gen-index ./cmd/gen-index

COPY --from=collect /output /output
RUN /gen-index -dir /output -out /output/index.html

# ── Server ────────────────────────────────────────────────────────────────────
FROM caddy:alpine

COPY --from=web /output /srv
COPY Caddyfile /etc/caddy/Caddyfile
