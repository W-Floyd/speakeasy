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
	MDNS       bool
	BT         bool
	IPv6       bool
	WiFi       string // "wstock" | "w9" | "wr" | "w9r" (default, no suffix)
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
	if v.MDNS {
		name += "-mdns"
	}
	if v.BT {
		name += "-bt"
	}
	if v.IPv6 {
		name += "-6"
	}
	if v.WiFi != "wstock" {
		name += "-" + v.WiFi
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
	if v.MDNS {
		parts = append(parts, "mDNS")
	}
	if v.BT {
		parts = append(parts, "Bluetooth")
	}
	if v.IPv6 {
		parts = append(parts, "IPv6")
	}
	switch v.WiFi {
	// wstock is the default, no label addition
	case "w9":
		parts = append(parts, "WiFi 9dBm")
	case "wr":
		parts = append(parts, "WiFi Stock Ramp")
	case "w9r":
		parts = append(parts, "WiFi 9dBm Ramp")
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
	if v.IPv6 {
		pkgs = append(pkgs, "common/ipv6.yaml")
	}
	switch v.WiFi {
	case "w9":
		pkgs = append(pkgs, "common/wifi-9.yaml")
	case "wr":
		pkgs = append(pkgs, "common/wifi-ramp.yaml")
	case "w9r":
		pkgs = append(pkgs, "common/wifi-9ramp.yaml")
	// wstock: no extra package
	}
	return pkgs
}

func generate(v variant) string {
	var sb strings.Builder

	fmt.Fprintf(&sb, "## %s - Edit the settings below.\n", v.friendlyName())
	sb.WriteString("substitutions:\n")
	fmt.Fprintf(&sb, "  name: %s\n", v.deviceName())
	fmt.Fprintf(&sb, "  friendly_name: %s\n", v.friendlyName())

	if v.Proto == "snapcast" && !v.MDNS {
		sb.WriteString("\n  # Snapcast server address and port\n")
		sb.WriteString("  snapcast_server_ip: \"192.168.1.1\"\n")
		sb.WriteString("  snapcast_server_port: \"1704\"\n")
	}

	sb.WriteString("\npackages:\n")
	for _, pkg := range v.packages() {
		fmt.Fprintf(&sb, "  - !include %s\n", pkg)
	}

	sb.WriteString("\ndashboard_import:\n")
	fmt.Fprintf(&sb, "  package_import_url: github://W-Floyd/speakeasy/%s@main\n", v.filename())
	sb.WriteString("  import_full_config: false\n")

	sb.WriteString("\nesphome:\n")
	sb.WriteString("  name: ${name}\n")
	sb.WriteString("  friendly_name: ${friendly_name}\n")

	if v.Proto == "snapcast" && v.MDNS {
		sb.WriteString("\nmedia_player:\n")
		sb.WriteString("  - id: !extend snapclient_media_player\n")
		sb.WriteString("    hostname: !remove\n")
		sb.WriteString("    port: !remove\n")
	}

	return sb.String()
}

func allVariants() []variant {
	var variants []variant
	for _, proto := range []string{"sendspin", "snapcast"} {
		for _, twoChannel := range []bool{false, true} {
			for _, mdns := range []bool{false, true} {
				// Sendspin is always mDNS; skip the non-mDNS case
				if proto == "sendspin" && !mdns {
					continue
				}
				for _, bt := range []bool{false, true} {
					for _, ipv6 := range []bool{false, true} {
						for _, wifi := range []string{"wstock", "w9", "wr", "w9r"} {
							variants = append(variants, variant{
								Proto:      proto,
								TwoChannel: twoChannel,
								MDNS:       mdns,
								BT:         bt,
								IPv6:       ipv6,
								WiFi:       wifi,
							})
						}
					}
				}
			}
		}
	}
	return variants
}

func main() {
	dir := flag.String("dir", ".", "directory to write firmware config files")
	flag.Parse()

	for _, v := range allVariants() {
		path := filepath.Join(*dir, v.filename())
		if err := os.WriteFile(path, []byte(generate(v)), 0644); err != nil {
			fmt.Fprintf(os.Stderr, "error writing %s: %v\n", path, err)
			os.Exit(1)
		}
		fmt.Println(v.filename())
	}
}
