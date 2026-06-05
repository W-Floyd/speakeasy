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

# ── speakeasy-ss-6
FROM esphome-ss AS esphome-ss-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-6 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc
FROM esphome-ss-6 AS esphome-sc
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc && \
    cp -r "${build_dir}/." /output/speakeasy-sc/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-6
FROM esphome-sc AS esphome-sc-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt
FROM esphome-sc-6 AS esphome-ss-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt-6
FROM esphome-ss-bt AS esphome-ss-bt-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt-6 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt
FROM esphome-ss-bt-6 AS esphome-sc-bt
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6
FROM esphome-sc-bt AS esphome-sc-bt-6
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-w9
FROM esphome-sc-bt-6 AS esphome-ss-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-6-w9
FROM esphome-ss-w9 AS esphome-ss-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-w9
FROM esphome-ss-6-w9 AS esphome-sc-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-6-w9
FROM esphome-sc-w9 AS esphome-sc-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt-w9
FROM esphome-sc-6-w9 AS esphome-ss-bt-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt-6-w9
FROM esphome-ss-bt-w9 AS esphome-ss-bt-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-w9
FROM esphome-ss-bt-6-w9 AS esphome-sc-bt-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6-w9
FROM esphome-sc-bt-w9 AS esphome-sc-bt-6-w9
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6-w9 \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6-w9.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6-w9.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6-w9 && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6-w9/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-wr
FROM esphome-sc-bt-6-w9 AS esphome-ss-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-6-wr
FROM esphome-ss-wr AS esphome-ss-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-wr
FROM esphome-ss-6-wr AS esphome-sc-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-6-wr
FROM esphome-sc-wr AS esphome-sc-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt-wr
FROM esphome-sc-6-wr AS esphome-ss-bt-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt-6-wr
FROM esphome-ss-bt-wr AS esphome-ss-bt-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-wr
FROM esphome-ss-bt-6-wr AS esphome-sc-bt-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6-wr
FROM esphome-sc-bt-wr AS esphome-sc-bt-6-wr
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6-wr \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6-wr.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6-wr.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6-wr && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6-wr/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-w9r
FROM esphome-sc-bt-6-wr AS esphome-ss-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-6-w9r
FROM esphome-ss-w9r AS esphome-ss-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-w9r
FROM esphome-ss-6-w9r AS esphome-sc-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-6-w9r
FROM esphome-sc-w9r AS esphome-sc-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt-w9r
FROM esphome-sc-6-w9r AS esphome-ss-bt-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-ss-bt-6-w9r
FROM esphome-ss-bt-w9r AS esphome-ss-bt-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-ss-bt-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-ss-bt-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-ss-bt-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-ss-bt-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-ss-bt-6-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-w9r
FROM esphome-ss-bt-6-w9r AS esphome-sc-bt-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-w9r/ && \
    rm -rf "${build_dir}"

# ── speakeasy-sc-bt-6-w9r
FROM esphome-sc-bt-w9r AS esphome-sc-bt-6-w9r
RUN --mount=type=cache,target=/root/.ccache,id=ccache \
    --mount=type=cache,target=/config/.esphome,id=esphome-sc-bt-6-w9r \
    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest speakeasy-sc-bt-6-w9r.yaml && \
    name=$(yq '.substitutions.name' speakeasy-sc-bt-6-w9r.yaml) && \
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1) && \
    mkdir -p /output/speakeasy-sc-bt-6-w9r && \
    cp -r "${build_dir}/." /output/speakeasy-sc-bt-6-w9r/ && \
    rm -rf "${build_dir}"

# ── Snapclient base ──────────────────────────────────────────────────────────
FROM espressif/idf:v5.5.1 AS snapclient-base

SHELL ["/bin/bash", "-c"]
WORKDIR /snapclient
COPY snapclient/ .
COPY snapclient-kconfig/ /snapclient-kconfig/

# ── snapclient-mdns
FROM snapclient-base AS snapclient-mdns
RUN --mount=type=cache,target=/root/.ccache,id=snapclient-ccache-mdns \
    source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.mdns" \
      -B build-mdns \
      build && \
    idf.py -B build-mdns merge-bin && \
    mkdir -p /output/snapclient-mdns && \
    cp build-mdns/merged-binary.bin /output/snapclient-mdns/merged.bin && \
    printf '{"name":"Snapclient mdns","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-mdns/manifest.json

# ── snapclient-mdns-w9
FROM snapclient-base AS snapclient-mdns-w9
RUN --mount=type=cache,target=/root/.ccache,id=snapclient-ccache-mdns-w9 \
    source /opt/esp/idf/export.sh && \
    idf.py \
      -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.mdns-w9" \
      -B build-mdns-w9 \
      build && \
    idf.py -B build-mdns-w9 merge-bin && \
    mkdir -p /output/snapclient-mdns-w9 && \
    cp build-mdns-w9/merged-binary.bin /output/snapclient-mdns-w9/merged.bin && \
    printf '{"name":"Snapclient mdns w9","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
      > /output/snapclient-mdns-w9/manifest.json

# ── Collect ──────────────────────────────────────────────────────────────────
FROM alpine AS collect
COPY --from=esphome-sc-bt-6-w9r /output /output
COPY --from=snapclient-mdns /output/snapclient-mdns /output/snapclient-mdns
COPY --from=snapclient-mdns-w9 /output/snapclient-mdns-w9 /output/snapclient-mdns-w9

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
