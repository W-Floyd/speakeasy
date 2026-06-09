package main

import (
	_ "embed"
	"bytes"
	"encoding/json"
	"flag"
	"html/template"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/extension"
	"github.com/yuin/goldmark/renderer/html"
)

//go:embed template.html
var page string

type firmware struct {
	Label       string
	Desc        string
	Manifest    string
	OTA         string
	OTAManifest string
	SizeReport  template.JS // JSON-encoded string or "null"
}

type group struct {
	Name  string
	Items []firmware
}

type doc struct {
	Name string
	HTML template.HTML
}

type pageData struct {
	Groups []group
	Docs   []doc
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
		"snapclient-mdns":        {Label: "mDNS", Desc: "CarlosDerSeher/snapclient — bare ESP-IDF, mDNS discovery"},
		"snapclient-mdns-nopull": {Label: "mDNS (no pull OTA)", Desc: "CarlosDerSeher/snapclient — bare ESP-IDF, mDNS discovery, pull OTA disabled"},
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

var md = goldmark.New(
	goldmark.WithExtensions(extension.GFM),
	goldmark.WithRendererOptions(html.WithUnsafe()),
)

func renderDocs(docsDir string) []doc {
	entries, err := os.ReadDir(docsDir)
	if err != nil {
		return nil
	}
	var docs []doc
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".md") {
			continue
		}
		src, err := os.ReadFile(filepath.Join(docsDir, e.Name()))
		if err != nil {
			continue
		}
		var buf bytes.Buffer
		if err := md.Convert(src, &buf); err != nil {
			continue
		}
		name := strings.TrimSuffix(e.Name(), ".md")
		name = strings.ReplaceAll(name, "-", " ")
		name = strings.ToUpper(name[:1]) + name[1:]
		docs = append(docs, doc{Name: name, HTML: template.HTML(buf.String())})
	}
	return docs
}

// copyDocAssets copies non-.md files from docsDir into outDir/docs/.
func copyDocAssets(docsDir, outDir string) error {
	entries, err := os.ReadDir(docsDir)
	if err != nil {
		return nil // no docs dir — not an error
	}
	dest := filepath.Join(outDir, "docs")
	for _, e := range entries {
		if e.IsDir() || strings.HasSuffix(e.Name(), ".md") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(docsDir, e.Name()))
		if err != nil {
			return err
		}
		if err := os.MkdirAll(dest, 0755); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(dest, e.Name()), data, 0644); err != nil {
			return err
		}
	}
	return nil
}

func main() {
	dir := flag.String("dir", ".", "directory containing firmware subdirectories")
	docsDir := flag.String("docs", "docs", "directory containing markdown doc files")
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
		sizeReport := template.JS("null")
		if data, err := os.ReadFile(filepath.Join(*dir, entry.Name(), "size.json")); err == nil {
			if json.Valid(data) {
				sizeReport = template.JS(data)
			}
		}
		groups[g].Items = append(groups[g].Items, firmware{
			Label:       meta.Label,
			Desc:        meta.Desc,
			Manifest:    entry.Name() + "/manifest.json",
			OTA:         ota,
			OTAManifest: otaManifest,
			SizeReport:  sizeReport,
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

	if err := copyDocAssets(*docsDir, filepath.Dir(*out)); err != nil {
		panic(err)
	}

	data := pageData{
		Groups: result,
		Docs:   renderDocs(*docsDir),
	}

	tmpl := template.Must(template.New("page").Parse(page))
	if err := tmpl.Execute(f, data); err != nil {
		panic(err)
	}
}
