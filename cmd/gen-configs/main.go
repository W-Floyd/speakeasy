package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type variant struct {
	Proto      string
	TwoChannel bool
	BT         bool
}

func (v variant) filename() string {
	return "speakeasy-" + v.deviceName() + ".yaml"
}

func (v variant) protoShort() string {
	switch v.Proto {
	case "sendspin":
		return "ss"
	case "snapcast":
		return "sc"
	}
	return v.Proto
}

func (v variant) deviceName() string {
	name := v.protoShort()
	if v.TwoChannel {
		name += "-2ch"
	}
	if v.BT {
		name += "-bt"
	}

	return name
}

func (v variant) friendlyName() string {
	parts := []string{"Speakeasy"}
	switch v.Proto {
	case "sendspin":
		parts = append(parts, "Sendspin")
	case "snapcast":
		parts = append(parts, "Snapcast")
	}
	if v.TwoChannel {
		parts = append(parts, "2ch")
	}
	if v.BT {
		parts = append(parts, "Bluetooth")
	}
	return strings.Join(parts, " ")
}

func (v variant) packages() []string {
	pkgs := []string{"common/base.yaml"}
	if v.BT {
		pkgs = append(pkgs, "common/improv.yaml")
	}
	switch v.Proto {
	case "sendspin":
		pkgs = append(pkgs, "common/sendspin-audio.yaml")
	case "snapcast":
		pkgs = append(pkgs, "common/snapcast-audio.yaml")
	}
	if v.TwoChannel {
		pkgs = append(pkgs, "common/second-speaker.yaml")
	}
	pkgs = append(pkgs, "common/wifi-ramp.yaml")
	return pkgs
}

func generate(v variant) string {
	var sb strings.Builder

	fmt.Fprintf(&sb, "## %s - Edit the settings below.\n", v.friendlyName())
	sb.WriteString("substitutions:\n")
	fmt.Fprintf(&sb, "  name: %s\n", v.deviceName())
	fmt.Fprintf(&sb, "  friendly_name: %s\n", v.friendlyName())

	sb.WriteString("\npackages:\n")
	for _, pkg := range v.packages() {
		fmt.Fprintf(&sb, "  - !include %s\n", pkg)
	}

	sb.WriteString("\ndashboard_import:\n")
	fmt.Fprintf(&sb, "  package_import_url: github://W-Floyd/speakeasy/%s@main\n", v.filename())
	sb.WriteString("  import_full_config: false\n")

	sb.WriteString("\nesp32:\n")
	sb.WriteString("  variant: esp32s3\n")

	sb.WriteString("\nesphome:\n")
	sb.WriteString("  name: ${name}\n")
	sb.WriteString("  friendly_name: ${friendly_name}\n")

	if v.Proto == "snapcast" {
		sb.WriteString("\nmedia_player:\n")
		sb.WriteString("  - id: !extend snapclient_media_player\n")
		sb.WriteString("    hostname: !remove\n")
		sb.WriteString("    port: !remove\n")
	}

	return sb.String()
}

func allVariants() []variant {
	var variants []variant
	for _, bt := range []bool{false, true} {
		for _, proto := range []string{"sendspin", "snapcast"} {
			variants = append(variants, variant{
				Proto: proto,
				BT:    bt,
			})
		}
	}
	return variants
}

func main() {
	dir := flag.String("dir", ".", "directory to write firmware config files")
	dryRun := flag.Bool("dry-run", false, "print filenames in generation order without writing")
	flag.Parse()

	for _, v := range allVariants() {
		fmt.Println(v.filename())
		if *dryRun {
			continue
		}
		path := filepath.Join(*dir, v.filename())
		if err := os.WriteFile(path, []byte(generate(v)), 0644); err != nil {
			fmt.Fprintf(os.Stderr, "error writing %s: %v\n", path, err)
			os.Exit(1)
		}
	}
}
