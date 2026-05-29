package main

import (
	"flag"
	"fmt"
	"os"
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

func main() {
	variantsFile := flag.String("variants", "variants.yaml", "path to variants.yaml")
	outFile := flag.String("out", ".github/workflows/build.yaml", "output workflow file")
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
}
