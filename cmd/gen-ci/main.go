package main

import (
	"flag"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"text/template"
)

// Use [[ ]] delimiters so ${{ }} GitHub Actions expressions pass through untouched.
const workflowTmpl = `# Generated from variants.yaml — do not edit directly.
# Run: go run ./cmd/gen-ci
name: Build

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        yaml-file:
[[- range .CI]]
          - speakeasy-[[.]].yaml
[[- end]]

    steps:
      - uses: actions/checkout@v4

      - name: Cache PlatformIO
        uses: actions/cache@v4
        with:
          path: ~/.platformio
          key: pio-${{ runner.os }}-${{ hashFiles('common/base.yaml') }}
          restore-keys: pio-${{ runner.os }}-

      - name: Build ${{ matrix.yaml-file }}
        id: build
        uses: esphome/build-action@v6
        with:
          yaml-file: ${{ matrix.yaml-file }}
          complete-manifest: true

      - name: Stage firmware
        run: |
          stem="${{ matrix.yaml-file }}"
          stem="${stem%.yaml}"
          mkdir -p "output/${stem}"
          cp -r "${{ steps.build.outputs.name }}/." "output/${stem}/"

      - name: Upload firmware
        uses: actions/upload-artifact@v4
        with:
          name: esphome-${{ matrix.yaml-file }}
          path: output/
          retention-days: 90

[[if .SnapclientCI]]
  build-snapclient:
    runs-on: ubuntu-latest
    container:
      image: espressif/idf:v5.5.4
    strategy:
      fail-fast: false
      matrix:
        variant:
[[- range .SnapclientCI]]
          - [[.]]
[[- end]]

    steps:
      - uses: actions/checkout@v4

      - name: Init snapclient submodules
        run: |
          git config --global --add safe.directory "$GITHUB_WORKSPACE"
          git submodule update --init --recursive snapclient

      - name: Build ${{ matrix.variant }}
        shell: bash
        run: |
          source /opt/esp/idf/export.sh
          cd snapclient
          echo "$(git -C "${GITHUB_WORKSPACE}" rev-parse --short HEAD)" > version.txt
          idf.py \
            -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;${GITHUB_WORKSPACE}/snapclient-kconfig/sdkconfig.${{ matrix.variant }}" \
            -B "build-${{ matrix.variant }}" \
            build
          idf.py -B "build-${{ matrix.variant }}" merge-bin
          python3 -m esp_idf_size --format json "build-${{ matrix.variant }}/snapclient.map" > "build-${{ matrix.variant }}/size.json"

      - name: Stage firmware
        shell: bash
        run: |
          source /opt/esp/idf/export.sh > /dev/null
          variant="${{ matrix.variant }}"
          out="output/snapclient-${variant}"
          mkdir -p "${out}"
          cp "snapclient/build-${variant}/merged-binary.bin" "${out}/merged.bin"
          cp "snapclient/build-${variant}/snapclient.bin" "${out}/snapclient-${variant}-ota.bin"
          cp "snapclient/build-${variant}/size.json" "${out}/size.json"
          label="${variant//-/ }"
          printf '{"name":"Snapclient %s","version":"1","builds":[{"chipFamily":"ESP32-S3","parts":[{"path":"merged.bin","offset":0}]}]}' \
            "${label}" > "${out}/manifest.json"
          if ! grep -q "CONFIG_SNAPCLIENT_WEB_OTA_PULL=n" "${GITHUB_WORKSPACE}/snapclient-kconfig/sdkconfig.${variant}"; then
            _ota="${out}/snapclient-${variant}-ota.bin"
            file_sha=$(sha256sum "${_ota}" | cut -d' ' -f1)
            _info=$(python3 -m esptool image-info "${_ota}" 2>/dev/null)
            sc_sha=$(echo "${_info}" | awk '/^ELF file SHA256:/{print $4}')
            sc_ver=$(echo "${_info}" | awk '/^App version:/{print $3}')
            pages_base="https://w-floyd.github.io/speakeasy"
            printf '{"version":"%s","url":"%s/snapclient-%s/snapclient-%s-ota.bin","sha256":"%s","file_sha256":"%s","release_notes":"snapclient@%s"}' \
              "${sc_ver}" "${pages_base}" "${variant}" "${variant}" "${sc_sha}" "${file_sha}" "${sc_ver}" \
              > "${out}/ota-manifest.json"
          fi

      - name: Upload firmware
        uses: actions/upload-artifact@v4
        with:
          name: snapclient-${{ matrix.variant }}
          path: output/
          retention-days: 90

[[end]]
  deploy:
    if: github.ref == 'refs/heads/main'
    needs: [build, build-snapclient]
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}

    steps:
      - uses: actions/checkout@v4

      - name: Download all firmware
        uses: actions/download-artifact@v4
        with:
          path: public/
          pattern: '{esphome-*,snapclient-*}'
          merge-multiple: true

      - name: Generate flash page
        run: go run ./cmd/gen-index -dir public -out public/index.html

      - uses: actions/upload-pages-artifact@v3
        with:
          path: public/

      - name: Deploy to GitHub Pages
        id: deploy
        uses: actions/deploy-pages@v4
`

type config struct {
	CI           []string
	SnapclientCI []string
}

func loadConfig(path string) (config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return config{}, err
	}
	var cfg config
	var section string
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimRight(line, "\r")
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		if !strings.HasPrefix(trimmed, "-") && strings.HasSuffix(trimmed, ":") {
			section = strings.TrimSuffix(trimmed, ":")
			continue
		}
		if strings.HasPrefix(trimmed, "- ") {
			item := strings.TrimPrefix(trimmed, "- ")
			if section == "ci" {
				cfg.CI = append(cfg.CI, item)
			}
			if section == "snapclient-ci" {
				cfg.SnapclientCI = append(cfg.SnapclientCI, item)
			}
		}
	}
	return cfg, nil
}

func generateDockerfile(variants []string, snapclientVariants []string) string {
	var sb strings.Builder

	sb.WriteString("# syntax=docker/dockerfile:1\n")
	sb.WriteString("# Generated from speakeasy-*.yaml — do not edit directly.\n")
	sb.WriteString("# Run: go run ./cmd/gen-ci\n")

	sb.WriteString(`
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

`)

	// Stages are sequential: each inherits from the previous so ~/.platformio
	// accumulates through the chain without re-downloading. .esphome stays a
	// separate cache mount per stage to avoid bloating image layers.
	prevStage := "variants"

	for _, yaml := range variants {
		stem := strings.TrimSuffix(yaml, ".yaml")
		short := strings.TrimPrefix(stem, "speakeasy-")
		stage := "esphome-" + short

		fmt.Fprintf(&sb, "# ── %s\n", stem)
		fmt.Fprintf(&sb, "FROM %s AS %s\n", prevStage, stage)
		fmt.Fprintf(&sb, "RUN --mount=type=cache,target=/root/.ccache,id=ccache \\\n")
		fmt.Fprintf(&sb, "    --mount=type=cache,target=/config/.esphome,id=esphome-%s \\\n", short)
		prevStage = stage
		fmt.Fprintf(&sb, "    IDF_CCACHE_ENABLE=1 python3 /usr/local/lib/esphome-entrypoint.py --complete-manifest %s && \\\n", yaml)
		fmt.Fprintf(&sb, "    name=$(yq '.substitutions.name' %s) && \\\n", yaml)
		fmt.Fprintf(&sb, "    build_dir=$(find . -maxdepth 1 -type d -name \"${name}-*\" | head -1) && \\\n")
		fmt.Fprintf(&sb, "    mkdir -p /output/%s && \\\n", stem)
		fmt.Fprintf(&sb, "    cp -r \"${build_dir}/.\" /output/%s/ && \\\n", stem)
		fmt.Fprintf(&sb, "    rm -rf \"${build_dir}\"\n\n")
	}

	// All ESPHome firmware outputs have accumulated into the final stage.
	lastESPHomeStage := "esphome-" + strings.TrimPrefix(strings.TrimSuffix(variants[len(variants)-1], ".yaml"), "speakeasy-")

	if len(snapclientVariants) > 0 {
		sb.WriteString("# ── Snapclient base ──────────────────────────────────────────────────────────\n")
		sb.WriteString("FROM espressif/idf:v5.5.4 AS snapclient-base\n\n")
		sb.WriteString("SHELL [\"/bin/bash\", \"-c\"]\n")
		sb.WriteString("WORKDIR /snapclient\n")
		sb.WriteString("COPY snapclient/ .\n")
		sb.WriteString("COPY snapclient-kconfig/ /snapclient-kconfig/\n")
		sb.WriteString("ARG SPEAKEASY_VERSION\n")
		sb.WriteString("RUN echo \"${SPEAKEASY_VERSION}\" > version.txt\n\n")

		for _, variant := range snapclientVariants {
			stage := "snapclient-" + variant
			fmt.Fprintf(&sb, "# ── %s\n", stage)
			fmt.Fprintf(&sb, "FROM snapclient-base AS %s\n", stage)
			label := strings.ReplaceAll(variant, "-", " ")
			fmt.Fprintf(&sb, "RUN source /opt/esp/idf/export.sh && \\\n")
			fmt.Fprintf(&sb, "    idf.py \\\n")
			fmt.Fprintf(&sb, "      -DSDKCONFIG_DEFAULTS=\"sdkconfig.defaults;sdkconfig.defaults.esp32s3;/snapclient-kconfig/sdkconfig.%s\" \\\n", variant)
			fmt.Fprintf(&sb, "      -B build-%s \\\n", variant)
			fmt.Fprintf(&sb, "      build && \\\n")
			fmt.Fprintf(&sb, "    idf.py -B build-%s merge-bin && \\\n", variant)
			fmt.Fprintf(&sb, "    mkdir -p /output/snapclient-%s && \\\n", variant)
			fmt.Fprintf(&sb, "    python3 -m esp_idf_size --format json build-%s/snapclient.map > /output/snapclient-%s/size.json && \\\n", variant, variant)
			fmt.Fprintf(&sb, "    cp build-%s/merged-binary.bin /output/snapclient-%s/merged.bin && \\\n", variant, variant)
			fmt.Fprintf(&sb, "    cp build-%s/snapclient.bin /output/snapclient-%s/snapclient-%s-ota.bin && \\\n", variant, variant, variant)
			fmt.Fprintf(&sb, "    printf '{\"name\":\"Snapclient %s\",\"version\":\"1\",\"builds\":[{\"chipFamily\":\"ESP32-S3\",\"parts\":[{\"path\":\"merged.bin\",\"offset\":0}]}]}' \\\n", label)
			if !strings.HasSuffix(variant, "nopull") {
				fmt.Fprintf(&sb, "      > /output/snapclient-%s/manifest.json && \\\n", variant)
				fmt.Fprintf(&sb, "    _ota=/output/snapclient-%s/snapclient-%s-ota.bin && \\\n", variant, variant)
				fmt.Fprintf(&sb, "    file_sha=$(sha256sum \"${_ota}\" | cut -d' ' -f1) && \\\n")
				fmt.Fprintf(&sb, "    _info=$(python3 -m esptool image-info \"${_ota}\" 2>/dev/null) && \\\n")
				fmt.Fprintf(&sb, "    sc_sha=$(echo \"${_info}\" | awk '/^ELF file SHA256:/{print $4}') && \\\n")
				fmt.Fprintf(&sb, "    sc_ver=$(echo \"${_info}\" | awk '/^App version:/{print $3}') && \\\n")
				fmt.Fprintf(&sb, "    pages_base=\"https://w-floyd.github.io/speakeasy\" && \\\n")
				fmt.Fprintf(&sb, "    printf '{\"version\":\"%%s\",\"url\":\"%%s/snapclient-%s/snapclient-%s-ota.bin\",\"sha256\":\"%%s\",\"file_sha256\":\"%%s\",\"release_notes\":\"snapclient@%%s\"}' \\\n", variant, variant)
				fmt.Fprintf(&sb, "      \"${sc_ver}\" \"${pages_base}\" \"${sc_sha}\" \"${file_sha}\" \"${sc_ver}\" \\\n")
				fmt.Fprintf(&sb, "      > /output/snapclient-%s/ota-manifest.json\n\n", variant)
			} else {
				fmt.Fprintf(&sb, "      > /output/snapclient-%s/manifest.json\n\n", variant)
			}
		}
	}

	sb.WriteString("# ── Collect ──────────────────────────────────────────────────────────────────\n")
	sb.WriteString("FROM alpine AS collect\n")
	fmt.Fprintf(&sb, "COPY --from=%s /output /output\n", lastESPHomeStage)
	for _, variant := range snapclientVariants {
		fmt.Fprintf(&sb, "COPY --from=snapclient-%s /output/snapclient-%s /output/snapclient-%s\n", variant, variant, variant)
	}

	sb.WriteString(`
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
`)

	return sb.String()
}

func main() {
	variantsFile := flag.String("variants", "variants.yaml", "path to variants.yaml")
	outFile := flag.String("out", ".github/workflows/build.yaml", "output workflow file")
	dockerFile := flag.String("dockerfile", "Dockerfile", "output Dockerfile")
	flag.Parse()

	cfg, err := loadConfig(*variantsFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error reading %s: %v\n", *variantsFile, err)
		os.Exit(1)
	}

	tmpl := template.Must(template.New("workflow").Delims("[[", "]]").Parse(workflowTmpl))
	f, err := os.Create(*outFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error creating %s: %v\n", *outFile, err)
		os.Exit(1)
	}
	defer f.Close()
	if err := tmpl.Execute(f, cfg); err != nil {
		fmt.Fprintf(os.Stderr, "error writing %s: %v\n", *outFile, err)
		os.Exit(1)
	}
	fmt.Printf("wrote %s (%d CI variants)\n", *outFile, len(cfg.CI))

	// Run gen-configs to get variants in their component-optimised order.
	out, err := exec.Command("go", "run", "./cmd/gen-configs", "--dry-run").Output()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error running gen-configs: %v\n", err)
		os.Exit(1)
	}
	var yamls []string
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		if line != "" {
			yamls = append(yamls, line)
		}
	}

	if err := os.WriteFile(*dockerFile, []byte(generateDockerfile(yamls, cfg.SnapclientCI)), 0644); err != nil {
		fmt.Fprintf(os.Stderr, "error writing %s: %v\n", *dockerFile, err)
		os.Exit(1)
	}
	fmt.Printf("wrote %s (%d firmware stages)\n", *dockerFile, len(yamls))
}
