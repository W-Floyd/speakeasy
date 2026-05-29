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

# ── speakeasy-sc-6-w9
FROM variants AS firmware-sc-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-6-w9r
FROM firmware-sc-6-w9 AS firmware-sc-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-6-wr
FROM firmware-sc-6-w9r AS firmware-sc-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-6
FROM firmware-sc-6-wr AS firmware-sc-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6-w9
FROM firmware-sc-6 AS firmware-sc-bt-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6-w9r
FROM firmware-sc-bt-6-w9 AS firmware-sc-bt-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6-wr
FROM firmware-sc-bt-6-w9r AS firmware-sc-bt-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6
FROM firmware-sc-bt-6-wr AS firmware-sc-bt-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-w9
FROM firmware-sc-bt-6 AS firmware-sc-bt-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-w9r
FROM firmware-sc-bt-w9 AS firmware-sc-bt-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-wr
FROM firmware-sc-bt-w9r AS firmware-sc-bt-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt
FROM firmware-sc-bt-wr AS firmware-sc-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-6-w9
FROM firmware-sc-bt AS firmware-sc-mdns-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-6-w9r
FROM firmware-sc-mdns-6-w9 AS firmware-sc-mdns-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-6-wr
FROM firmware-sc-mdns-6-w9r AS firmware-sc-mdns-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-6
FROM firmware-sc-mdns-6-wr AS firmware-sc-mdns-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-6 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt-6-w9
FROM firmware-sc-mdns-6 AS firmware-sc-mdns-bt-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt-6-w9r
FROM firmware-sc-mdns-bt-6-w9 AS firmware-sc-mdns-bt-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt-6-wr
FROM firmware-sc-mdns-bt-6-w9r AS firmware-sc-mdns-bt-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt-6
FROM firmware-sc-mdns-bt-6-wr AS firmware-sc-mdns-bt-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt-6 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt-w9
FROM firmware-sc-mdns-bt-6 AS firmware-sc-mdns-bt-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt-w9r
FROM firmware-sc-mdns-bt-w9 AS firmware-sc-mdns-bt-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt-wr
FROM firmware-sc-mdns-bt-w9r AS firmware-sc-mdns-bt-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-bt
FROM firmware-sc-mdns-bt-wr AS firmware-sc-mdns-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-bt && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-w9
FROM firmware-sc-mdns-bt AS firmware-sc-mdns-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-w9r
FROM firmware-sc-mdns-w9 AS firmware-sc-mdns-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns-wr
FROM firmware-sc-mdns-w9r AS firmware-sc-mdns-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-mdns
FROM firmware-sc-mdns-wr AS firmware-sc-mdns
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-mdns \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-mdns.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-mdns.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-mdns && \
    cp -r "${build_dir}/." /output/speakeasy-sc-mdns/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-w9
FROM firmware-sc-mdns AS firmware-sc-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-w9r
FROM firmware-sc-w9 AS firmware-sc-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-wr
FROM firmware-sc-w9r AS firmware-sc-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc
FROM firmware-sc-wr AS firmware-sc
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc && \
    cp -r "${build_dir}/." /output/speakeasy-sc/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-6-w9
FROM firmware-sc AS firmware-ss-mdns-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-6-w9r
FROM firmware-ss-mdns-6-w9 AS firmware-ss-mdns-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-6-wr
FROM firmware-ss-mdns-6-w9r AS firmware-ss-mdns-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-6
FROM firmware-ss-mdns-6-wr AS firmware-ss-mdns-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-6 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt-6-w9
FROM firmware-ss-mdns-6 AS firmware-ss-mdns-bt-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt-6-w9r
FROM firmware-ss-mdns-bt-6-w9 AS firmware-ss-mdns-bt-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt-6-wr
FROM firmware-ss-mdns-bt-6-w9r AS firmware-ss-mdns-bt-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt-6
FROM firmware-ss-mdns-bt-6-wr AS firmware-ss-mdns-bt-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt-6 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt-w9
FROM firmware-ss-mdns-bt-6 AS firmware-ss-mdns-bt-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt-w9r
FROM firmware-ss-mdns-bt-w9 AS firmware-ss-mdns-bt-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt-wr
FROM firmware-ss-mdns-bt-w9r AS firmware-ss-mdns-bt-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-bt
FROM firmware-ss-mdns-bt-wr AS firmware-ss-mdns-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-bt && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-w9
FROM firmware-ss-mdns-bt AS firmware-ss-mdns-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-w9r
FROM firmware-ss-mdns-w9 AS firmware-ss-mdns-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns-wr
FROM firmware-ss-mdns-w9r AS firmware-ss-mdns-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-mdns
FROM firmware-ss-mdns-wr AS firmware-ss-mdns
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-mdns \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-mdns.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-mdns.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-mdns && \
    cp -r "${build_dir}/." /output/speakeasy-ss-mdns/ && \
    rm -rf "${build_dir}"

# ── Collect ──────────────────────────────────────────────────────────────────
FROM alpine AS collect
COPY --from=firmware-ss-mdns /output /output

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
