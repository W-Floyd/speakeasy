package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
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
          name: firmware-${{ matrix.yaml-file }}
          path: output/
          retention-days: 90

  deploy:
    if: github.ref == 'refs/heads/main'
    needs: build
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
          pattern: firmware-*
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
	CI []string
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
		}
	}
	return cfg, nil
}

func generateDockerfile(variants []string) string {
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
		stage := "firmware-" + short

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

	// All firmware outputs have accumulated into the final stage.
	lastStage := "firmware-" + strings.TrimPrefix(strings.TrimSuffix(variants[len(variants)-1], ".yaml"), "speakeasy-")
	sb.WriteString("# ── Collect ──────────────────────────────────────────────────────────────────\n")
	sb.WriteString("FROM alpine AS collect\n")
	fmt.Fprintf(&sb, "COPY --from=%s /output /output\n", lastStage)

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

	yamls, err := filepath.Glob("speakeasy-*.yaml")
	if err != nil {
		fmt.Fprintf(os.Stderr, "error globbing yaml files: %v\n", err)
		os.Exit(1)
	}
	sort.Strings(yamls)

	if err := os.WriteFile(*dockerFile, []byte(generateDockerfile(yamls)), 0644); err != nil {
		fmt.Fprintf(os.Stderr, "error writing %s: %v\n", *dockerFile, err)
		os.Exit(1)
	}
	fmt.Printf("wrote %s (%d firmware stages)\n", *dockerFile, len(yamls))
}
