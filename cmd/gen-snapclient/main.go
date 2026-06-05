package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// base holds the hardware constants for this board. These never vary across builds.
const base = `# Hardware: ESP32-S3 Supermini + MAX98357A
# SD_MODE is tied to a L+R/2 voltage divider for hardware mono mix — no mute GPIO needed.
CONFIG_AUDIO_BOARD_CUSTOM=y
CONFIG_DAC_MAX98357=y
CONFIG_MASTER_I2S_BCK_PIN=11
CONFIG_MASTER_I2S_LRCK_PIN=10
CONFIG_MASTER_I2S_DATAOUT_PIN=12
CONFIG_SPIRAM_MODE_QUAD=y
CONFIG_ESP32S3_DEFAULT_CPU_FREQ_240=y
CONFIG_ESP32S3_DATA_CACHE_64KB=y
CONFIG_ESP32S3_DATA_CACHE_LINE_64B=y
CONFIG_ESP32S3_INSTRUCTION_CACHE_32KB=y
CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP=y
CONFIG_ESP32_WIFI_STATIC_RX_BUFFER_NUM=16
CONFIG_ESP32_WIFI_DYNAMIC_RX_BUFFER_NUM=64
CONFIG_ESPTOOLPY_FLASHMODE_QIO=y
CONFIG_ESPTOOLPY_FLASHFREQ_80M=y
# WiFi IRAM opts are counterproductive on ESP32-S3 (WiFi code is mapped to IRAM by default).
CONFIG_ESP_WIFI_IRAM_OPT=n
CONFIG_ESP_WIFI_RX_IRAM_OPT=n
# WiFi provisioning via Improv serial — configure credentials at https://web.esphome.io/
CONFIG_ENABLE_WIFI_PROVISIONING=y
# Light sleep gates USB clocks on ESP32-S3, breaking USB Serial JTAG used by Improv.
CONFIG_PM_ENABLE=n
`

type discovery struct {
	name    string
	comment string
	config  string
}

type wifiPower struct {
	suffix  string // empty = stock (no suffix in filename)
	comment string
	config  string
}

var discoveries = []discovery{
	{
		name:    "mdns",
		comment: "Discovery: mDNS — server located automatically on the local network",
		config:  "CONFIG_SNAPSERVER_USE_MDNS=y\n",
	},
}

var wifiPowers = []wifiPower{
	{suffix: ""},
	{
		suffix:  "w9",
		comment: "WiFi TX power: ~8.5 dBm — compact PCB antenna self-interferes at high power",
		// CONFIG_ESP_PHY_MAX_TX_POWER is in dBm, minimum 10 via kconfig.
		// For the full 8.5 dBm match, also call esp_wifi_set_max_tx_power(34)
		// at runtime in components/network_interface/ after WiFi init.
		config: "CONFIG_ESP_PHY_MAX_TX_POWER=10\n",
	},
}

func variantName(d discovery, w wifiPower) string {
	if w.suffix == "" {
		return d.name
	}
	return d.name + "-" + w.suffix
}

func generate(d discovery, w wifiPower) string {
	var sb strings.Builder
	fmt.Fprintf(&sb, "# Generated from cmd/gen-snapclient — do not edit directly.\n")
	fmt.Fprintf(&sb, "# Run: go run ./cmd/gen-snapclient\n")
	fmt.Fprintf(&sb, "# Variant: %s\n\n", variantName(d, w))
	sb.WriteString(base)
	sb.WriteString("\n# ")
	sb.WriteString(d.comment)
	sb.WriteString("\n")
	sb.WriteString(d.config)
	if w.suffix != "" {
		sb.WriteString("\n# ")
		sb.WriteString(w.comment)
		sb.WriteString("\n")
		sb.WriteString(w.config)
	}
	return sb.String()
}

func main() {
	dir := flag.String("dir", "snapclient-kconfig", "output directory for sdkconfig defaults files")
	dryRun := flag.Bool("dry-run", false, "print filenames in generation order without writing")
	flag.Parse()

	if !*dryRun {
		if err := os.MkdirAll(*dir, 0755); err != nil {
			fmt.Fprintf(os.Stderr, "error creating %s: %v\n", *dir, err)
			os.Exit(1)
		}
	}

	for _, d := range discoveries {
		for _, w := range wifiPowers {
			filename := "sdkconfig." + variantName(d, w)
			fmt.Println(filename)
			if *dryRun {
				continue
			}
			path := filepath.Join(*dir, filename)
			if err := os.WriteFile(path, []byte(generate(d, w)), 0644); err != nil {
				fmt.Fprintf(os.Stderr, "error writing %s: %v\n", path, err)
				os.Exit(1)
			}
		}
	}
}
