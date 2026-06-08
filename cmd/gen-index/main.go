package main

import (
	_ "embed"
	"flag"
	"html/template"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

//go:embed template.html
var page string

type firmware struct {
	Label       string
	Desc        string
	Manifest    string
	OTA         string
	OTAManifest string
}

type group struct {
	Name  string
	Items []firmware
}

var groupOrder = []string{"Sendspin", "Snapcast", "Snapcast (standalone)"}

var known = buildKnown()

func buildKnown() map[string]firmware {
	type protoSpec struct {
		id    string
		label string
		desc  string
	}
	protos := []protoSpec{
		{id: "ss", label: "Sendspin", desc: "Music Assistant via Sendspin"},
		{id: "sc", label: "Snapcast", desc: "Snapcast client (mDNS discovery)"},
	}
	m := map[string]firmware{
		"snapclient-mdns": {Label: "mDNS", Desc: "CarlosDerSeher/snapclient — bare ESP-IDF, mDNS discovery"},
	}
	for _, p := range protos {
		for _, bt := range []bool{false, true} {
			key := "speakeasy-" + p.id
			label := p.label
			desc := p.desc
			if bt {
				key += "-bt"
				label += " Bluetooth"
			}
			m[key] = firmware{Label: label, Desc: desc}
		}
	}
	return m
}

func groupOf(dir string) string {
	if strings.HasPrefix(dir, "snapclient-") {
		return "Snapcast (standalone)"
	}
	if strings.HasPrefix(dir, "speakeasy-sc") {
		return "Snapcast"
	}
	return "Sendspin"
}

func derive(dir string) firmware {
	name := strings.TrimPrefix(strings.TrimPrefix(dir, "speakeasy-"), "snapclient-")
	parts := strings.Split(name, "-")
	for i, p := range parts {
		switch p {
		case "ss":
			parts[i] = "Sendspin"
		case "sc":
			parts[i] = "Snapcast"
		case "bt":
			parts[i] = "BT"
		case "6":
			parts[i] = "IPv6"
		case "w9":
			parts[i] = "WiFi 9dBm"
		case "wr":
			parts[i] = "WiFi Stock Ramp"
		case "w9r":
			parts[i] = "WiFi 9dBm Ramp"
		default:
			parts[i] = strings.ToUpper(p[:1]) + p[1:]
		}
	}
	return firmware{Label: strings.Join(parts, " ")}
}

func main() {
	dir := flag.String("dir", ".", "directory containing firmware subdirectories")
	out := flag.String("out", "index.html", "output HTML file")
	flag.Parse()

	entries, err := os.ReadDir(*dir)
	if err != nil {
		panic(err)
	}

	groups := map[string]*group{}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		if _, err := os.Stat(filepath.Join(*dir, entry.Name(), "manifest.json")); err != nil {
			continue
		}
		meta, ok := known[entry.Name()]
		if !ok {
			meta = derive(entry.Name())
		}
		g := groupOf(entry.Name())
		if groups[g] == nil {
			groups[g] = &group{Name: g}
		}
		ota := ""
		otaFile := entry.Name() + "-ota.bin"
		if _, err := os.Stat(filepath.Join(*dir, entry.Name(), otaFile)); err == nil {
			ota = entry.Name() + "/" + otaFile
		}
		otaManifest := ""
		if _, err := os.Stat(filepath.Join(*dir, entry.Name(), "ota-manifest.json")); err == nil {
			otaManifest = entry.Name() + "/ota-manifest.json"
		}
		groups[g].Items = append(groups[g].Items, firmware{
			Label:       meta.Label,
			Desc:        meta.Desc,
			Manifest:    entry.Name() + "/manifest.json",
			OTA:         ota,
			OTAManifest: otaManifest,
		})
	}

	var result []group
	for _, name := range groupOrder {
		if g, ok := groups[name]; ok {
			sort.Slice(g.Items, func(i, j int) bool {
				return g.Items[i].Label < g.Items[j].Label
			})
			result = append(result, *g)
		}
	}

	f, err := os.Create(*out)
	if err != nil {
		panic(err)
	}
	defer f.Close()

	tmpl := template.Must(template.New("page").Parse(page))
	if err := tmpl.Execute(f, result); err != nil {
		panic(err)
	}
}
