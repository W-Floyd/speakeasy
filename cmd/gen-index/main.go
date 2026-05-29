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
	Label    string
	Desc     string
	Manifest string
}

type group struct {
	Name  string
	Items []firmware
}

var groupOrder = []string{"Sendspin", "Snapcast"}

var known = map[string]firmware{
	"speakeasy-sendspin":          {Label: "Sendspin", Desc: "Music Assistant via Sendspin"},
	"speakeasy-sendspin-2ch":      {Label: "Sendspin 2ch", Desc: "Dual I2S output, Music Assistant via Sendspin"},
	"speakeasy-snapcast":          {Label: "Snapcast", Desc: "Snapcast client (server IP)"},
	"speakeasy-snapcast-m":        {Label: "Snapcast mDNS", Desc: "Snapcast client (mDNS discovery)"},
	"speakeasy-snapcast-2ch":      {Label: "Snapcast 2ch", Desc: "Dual I2S output, Snapcast client (server IP)"},
	"speakeasy-snapcast-2ch-m":    {Label: "Snapcast 2ch mDNS", Desc: "Dual I2S output, Snapcast client (mDNS discovery)"},
}

func groupOf(dir string) string {
	if strings.Contains(dir, "snapcast") {
		return "Snapcast"
	}
	return "Sendspin"
}

func derive(dir string) firmware {
	name := strings.TrimPrefix(dir, "speakeasy-")
	parts := strings.Split(name, "-")
	for i, p := range parts {
		switch p {
		case "mdns":
			parts[i] = "mDNS"
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
		groups[g].Items = append(groups[g].Items, firmware{
			Label:    meta.Label,
			Desc:     meta.Desc,
			Manifest: entry.Name() + "/manifest.json",
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
