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

# ── speakeasy-ots-ss
FROM variants AS esphome-ots-ss
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ots-ss \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ots-ss.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ots-ss.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ots-ss && \
    cp -r "${build_dir}/." /output/speakeasy-ots-ss/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ots-sc
FROM esphome-ots-ss AS esphome-ots-sc
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ots-sc \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ots-sc.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ots-sc.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ots-sc && \
    cp -r "${build_dir}/." /output/speakeasy-ots-sc/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ots-ss-bt
FROM esphome-ots-sc AS esphome-ots-ss-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ots-ss-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ots-ss-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ots-ss-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ots-ss-bt && \
    cp -r "${build_dir}/." /output/speakeasy-ots-ss-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ots-sc-bt
FROM esphome-ots-ss-bt AS esphome-ots-sc-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ots-sc-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ots-sc-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ots-sc-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ots-sc-bt && \
    cp -r "${build_dir}/." /output/speakeasy-ots-sc-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-pcb-ss
FROM esphome-ots-sc-bt AS esphome-pcb-ss
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-pcb-ss \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-pcb-ss.yaml && \
    name=$(yq '.substitutions.name' speakeasy-pcb-ss.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-pcb-ss && \
    cp -r "${build_dir}/." /output/speakeasy-pcb-ss/ && \
    rm -rf "${build_dir}"

# ── speakeasy-pcb-sc
FROM esphome-pcb-ss AS esphome-pcb-sc
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-pcb-sc \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-pcb-sc.yaml && \
    name=$(yq '.substitutions.name' speakeasy-pcb-sc.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-pcb-sc && \
    cp -r "${build_dir}/." /output/speakeasy-pcb-sc/ && \
    rm -rf "${build_dir}"

# ── speakeasy-pcb-ss-bt
FROM esphome-pcb-sc AS esphome-pcb-ss-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-pcb-ss-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-pcb-ss-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-pcb-ss-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-pcb-ss-bt && \
    cp -r "${build_dir}/." /output/speakeasy-pcb-ss-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-pcb-sc-bt
FROM esphome-pcb-ss-bt AS esphome-pcb-sc-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-pcb-sc-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-pcb-sc-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-pcb-sc-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-pcb-sc-bt && \
    cp -r "${build_dir}/." /output/speakeasy-pcb-sc-bt/ && \
    rm -rf "${build_dir}"

# ── Snapclient base ──────────────────────────────────────────────────────────
FROM espressif/idf:v5.5.4 AS snapclient-base

SHELL ["/bin/bash", "-c"]
WORKDIR /snapclient
COPY snapclient/ .
COPY snapclient-kconfig/ /snapclient-kconfig/
ARG SPEAKEASY_VERSION
RUN echo "${SPEAKEASY_VERSION}" > version.txt

# ── snapclient-ots
FROM snapclient-base AS snapclient-ots
RUN source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.ots" \
      -B build-ots \
      build && \
    idf.py -B build-ots merge-bin && \
    mkdir -p /output/snapclient-ots && \
    python3 -m esp_idf_size --format json build-ots/snapclient.map > /output/snapclient-ots/size.json && \
    cp build-ots/merged-binary.bin /output/snapclient-ots/merged.bin && \
    cp build-ots/snapclient.bin /output/snapclient-ots/snapclient-ots-ota.bin && \
    printf '{"name":"Snapclient ots","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-ots/manifest.json && \
    _ota=/output/snapclient-ots/snapclient-ots-ota.bin && \
    file_sha=$(sha256sum "${_ota}" | cut -d' ' -f1) && \
    _info=$(esptool.py image_info --version 2 "${_ota}" 2>/dev/null) && \
    sc_sha=$(echo "${_info}" | awk '/^ELF file SHA256:/{print $4}') && \
    sc_ver=$(echo "${_info}" | awk '/^App version:/{print $3}') && \
    pages_base="https://w-floyd.github.io/speakeasy" && \
    printf '{"version":"%s","url":"%s/snapclient-ots/snapclient-ots-ota.bin","sha256":"%s","file_sha256":"%s","release_notes":"snapclient@%s"}' \
      "${sc_ver}" "${pages_base}" "${sc_sha}" "${file_sha}" "${sc_ver}" \
      > /output/snapclient-ots/ota-manifest.json

# ── snapclient-ots-nopull
FROM snapclient-base AS snapclient-ots-nopull
RUN source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.ots-nopull" \
      -B build-ots-nopull \
      build && \
    idf.py -B build-ots-nopull merge-bin && \
    mkdir -p /output/snapclient-ots-nopull && \
    python3 -m esp_idf_size --format json build-ots-nopull/snapclient.map > /output/snapclient-ots-nopull/size.json && \
    cp build-ots-nopull/merged-binary.bin /output/snapclient-ots-nopull/merged.bin && \
    cp build-ots-nopull/snapclient.bin /output/snapclient-ots-nopull/snapclient-ots-nopull-ota.bin && \
    printf '{"name":"Snapclient ots nopull","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-ots-nopull/manifest.json

# ── snapclient-pcb
FROM snapclient-base AS snapclient-pcb
RUN source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.pcb" \
      -B build-pcb \
      build && \
    idf.py -B build-pcb merge-bin && \
    mkdir -p /output/snapclient-pcb && \
    python3 -m esp_idf_size --format json build-pcb/snapclient.map > /output/snapclient-pcb/size.json && \
    cp build-pcb/merged-binary.bin /output/snapclient-pcb/merged.bin && \
    cp build-pcb/snapclient.bin /output/snapclient-pcb/snapclient-pcb-ota.bin && \
    printf '{"name":"Snapclient pcb","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-pcb/manifest.json && \
    _ota=/output/snapclient-pcb/snapclient-pcb-ota.bin && \
    file_sha=$(sha256sum "${_ota}" | cut -d' ' -f1) && \
    _info=$(esptool.py image_info --version 2 "${_ota}" 2>/dev/null) && \
    sc_sha=$(echo "${_info}" | awk '/^ELF file SHA256:/{print $4}') && \
    sc_ver=$(echo "${_info}" | awk '/^App version:/{print $3}') && \
    pages_base="https://w-floyd.github.io/speakeasy" && \
    printf '{"version":"%s","url":"%s/snapclient-pcb/snapclient-pcb-ota.bin","sha256":"%s","file_sha256":"%s","release_notes":"snapclient@%s"}' \
      "${sc_ver}" "${pages_base}" "${sc_sha}" "${file_sha}" "${sc_ver}" \
      > /output/snapclient-pcb/ota-manifest.json

# ── snapclient-pcb-nopull
FROM snapclient-base AS snapclient-pcb-nopull
RUN source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.pcb-nopull" \
      -B build-pcb-nopull \
      build && \
    idf.py -B build-pcb-nopull merge-bin && \
    mkdir -p /output/snapclient-pcb-nopull && \
    python3 -m esp_idf_size --format json build-pcb-nopull/snapclient.map > /output/snapclient-pcb-nopull/size.json && \
    cp build-pcb-nopull/merged-binary.bin /output/snapclient-pcb-nopull/merged.bin && \
    cp build-pcb-nopull/snapclient.bin /output/snapclient-pcb-nopull/snapclient-pcb-nopull-ota.bin && \
    printf '{"name":"Snapclient pcb nopull","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-pcb-nopull/manifest.json

# ── Collect ──────────────────────────────────────────────────────────────────
FROM alpine AS collect
COPY --from=esphome-pcb-sc-bt /output /output
COPY --from=snapclient-ots /output/snapclient-ots /output/snapclient-ots
COPY --from=snapclient-ots-nopull /output/snapclient-ots-nopull /output/snapclient-ots-nopull
COPY --from=snapclient-pcb /output/snapclient-pcb /output/snapclient-pcb
COPY --from=snapclient-pcb-nopull /output/snapclient-pcb-nopull /output/snapclient-pcb-nopull

# ── Web ───────────────────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS web

WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/root/.cache/go-build \
    go mod download
COPY cmd/ cmd/
RUN --mount=type=cache,target=/root/.cache/go-build \
    go build -o /gen-index ./cmd/gen-index

COPY --from=collect /output /output
COPY docs/ docs/
RUN /gen-index -dir /output -docs docs -out /output/index.html

# ── Server ────────────────────────────────────────────────────────────────────
FROM caddy:alpine
COPY --from=web /output /srv
COPY Caddyfile /etc/caddy/Caddyfile
