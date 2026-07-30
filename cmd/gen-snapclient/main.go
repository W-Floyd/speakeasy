package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// base is the overlay applied on top of sdkconfig.defaults + sdkconfig.defaults.esp32s3.
// Only includes settings that differ from or extend those upstream defaults.
// Non-essential tuning is commented out — enable incrementally to prove each change.
// Hardware-specific I2S pin assignments are injected per-hardware variant (see hardware type below).
const base = `# ── Essential: hardware identity ────────────────────────────────────────────
CONFIG_AUDIO_BOARD_CUSTOM=y
CONFIG_DAC_MAX98357=y
CONFIG_ESPTOOLPY_FLASHMODE_QIO=y
CONFIG_ESPTOOLPY_FLASHFREQ_80M=y

# ── Essential: PSRAM ─────────────────────────────────────────────────────────
# Override: upstream sdkconfig.defaults.esp32s3 sets OCT; this board has quad PSRAM only.
CONFIG_SPIRAM_MODE_QUAD=y
CONFIG_SPIRAM_BOOT_INIT=y
CONFIG_SPIRAM_USE_MALLOC=y
CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL=16384

# ── Essential: WiFi IRAM ─────────────────────────────────────────────────────
# Quad PSRAM does not map WiFi code to IRAM by default (unlike octal); these
# options are required to avoid WiFi ISR/receive latency spikes.
CONFIG_ESP_WIFI_IRAM_OPT=y
CONFIG_ESP_WIFI_RX_IRAM_OPT=y

# ── Essential: audio function ────────────────────────────────────────────────
# MAX98357A has no hardware volume control — use DSP-based software volume.
CONFIG_USE_DSP_PROCESSOR=y
CONFIG_USE_DSP_SOFT_CLIP=y
CONFIG_SNAPCLIENT_USE_SOFT_VOL=y
CONFIG_SNAPCLIENT_VOLUME_CURVE_DB_RANGE=40
# Compact PCB antenna self-interferes at high TX power; expose slider in web UI.
CONFIG_SNAPCLIENT_WIFI_TX_POWER_CONTROL=y

# ── Essential: WiFi provisioning ─────────────────────────────────────────────
# WiFi provisioning via Improv serial — configure credentials at https://web.esphome.io/
CONFIG_ENABLE_WIFI_PROVISIONING=y
# Light sleep gates USB clocks on ESP32-S3, breaking USB Serial JTAG used by Improv.
CONFIG_PM_ENABLE=n

# ── Essential: web server ────────────────────────────────────────────────────
CONFIG_WEB_PORT=80

# ── Tuning: CPU / cache ───────────────────────────────────────────────────────
CONFIG_ESP32S3_DEFAULT_CPU_FREQ_240=y
CONFIG_ESP32S3_DATA_CACHE_64KB=y
CONFIG_ESP32S3_DATA_CACHE_LINE_64B=y
CONFIG_ESP32S3_INSTRUCTION_CACHE_32KB=y

# ── Tuning: I2S / audio ──────────────────────────────────────────────────────
# I2S ISR in IRAM — keeps audio delivery safe when flash cache is disabled (OTA/NVS writes).
CONFIG_I2S_ISR_IRAM_SAFE=y

# ── Tuning: compiler ─────────────────────────────────────────────────────────
CONFIG_COMPILER_OPTIMIZATION_PERF=y

# ── Tuning: FreeRTOS ─────────────────────────────────────────────────────────
#CONFIG_FREERTOS_HZ=1000

# ── Tuning: WiFi buffers ─────────────────────────────────────────────────────
# Static RX/TX buffer counts left at defaults (8) — test device uses defaults.
CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM=64
CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM=32
CONFIG_ESP_WIFI_MGMT_SBUF_NUM=32

# ── Tuning: WiFi AMPDU ───────────────────────────────────────────────────────
CONFIG_ESP_WIFI_TX_BA_WIN=8
CONFIG_ESP_WIFI_RX_BA_WIN=16

# ── Tuning: WiFi IRAM (extra) ────────────────────────────────────────────────
# Additional frequently-called WiFi functions in IRAM; default off, reduces throughput when absent.
CONFIG_ESP_WIFI_EXTRA_IRAM_OPT=y

# ── Tuning: WiFi power management ────────────────────────────────────────────
# Prevent power save mode from activating on WiFi disconnect (avoids reconnect latency spike).
#CONFIG_ESP_WIFI_STA_DISCONNECTED_PM_ENABLE=n

# ── Tuning: LwIP ─────────────────────────────────────────────────────────────
# Pin LwIP/TCP to core 0 alongside WiFi, freeing core 1 for audio.
CONFIG_LWIP_TCPIP_TASK_AFFINITY_CPU0=y
# IRAM placement for LwIP RX/TX path: >10% TCP throughput, plus TCP-specific path.
CONFIG_LWIP_IRAM_OPTIMIZATION=y
CONFIG_LWIP_EXTRA_IRAM_OPTIMIZATION=y
# Larger windows, selective ACK, and buffers improve streaming smoothness.
CONFIG_LWIP_TCP_SND_BUF_DEFAULT=11520
CONFIG_LWIP_TCP_WND_DEFAULT=11520
CONFIG_LWIP_TCP_RECVMBOX_SIZE=16
CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=64
# Override: upstream sets 4; raise to 8 for smoother streaming.
CONFIG_LWIP_TCP_OOSEQ_MAX_PBUFS=8
CONFIG_LWIP_TCP_SACK_OUT=y

# ── Tuning: logging ───────────────────────────────────────────────────────────
# Zero logging overhead at runtime; level can be raised at runtime for debugging.
CONFIG_LOG_DEFAULT_LEVEL_NONE=y
CONFIG_LOG_MAXIMUM_LEVEL_INFO=y
`

const pagesBase = "https://w-floyd.github.io/speakeasy"

type discovery struct {
	name    string
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

type hardware struct {
	name    string
	comment string
	// i2sPins is the hardware-specific I2S pin block injected after the base identity section.
	i2sPins []string
}

// hardwares lists supported hardware targets.
// "ots" = off-the-shelf ESP32-S3 Supermini (pins match the generic supermini board).
// "pcb" = custom Speakeasy PCB (ESP32-S3-MINI-1U-N4R2; I2S pins from board_def.py).
var hardwares = []hardware{
	{
		name:    "ots",
		comment: "Hardware: off-the-shelf ESP32-S3 Supermini / Speakeasy Lowcost PCB — SD_MODE tied to L+R/2 voltage divider (hardware mono, no mute GPIO)",
		i2sPins: []string{
			// Matches circuit-synth-lowcost/board_def.py; LRCK/DATAOUT are
			// swapped relative to the custom PCB below.
			"CONFIG_MASTER_I2S_BCK_PIN=5",
			"CONFIG_MASTER_I2S_LRCK_PIN=4",
			"CONFIG_MASTER_I2S_DATAOUT_PIN=6",
		},
	},
	{
		name:    "pcb",
		comment: "Hardware: custom Speakeasy PCB (ESP32-S3-MINI-1U-N4R2) — SD_MODE driven via IO7/IO8 resistor network (see board_def.py)",
		i2sPins: []string{
			"CONFIG_MASTER_I2S_BCK_PIN=5",
			"CONFIG_MASTER_I2S_LRCK_PIN=6",
			"CONFIG_MASTER_I2S_DATAOUT_PIN=4",
			// "CONFIG_MAX98357_MUTE_PIN=8",
		},
	},
}

type otaPullMode struct {
	suffix  string
	enabled bool
}

var otaPullModes = []otaPullMode{
	{suffix: "", enabled: true},
	{suffix: "nopull", enabled: false},
}

func variantNameFor(h hardware, d discovery, p otaPullMode) string {
	name := h.name
	if len(discoveries) > 1 {
		name = name + "-" + d.name
	}
	if p.suffix != "" {
		name = name + "-" + p.suffix
	}
	return name
}

func generate(h hardware, d discovery, p otaPullMode) string {
	variantName := variantNameFor(h, d, p)

	var sb strings.Builder
	fmt.Fprintf(&sb, "# Generated from cmd/gen-snapclient — do not edit directly.\n")
	fmt.Fprintf(&sb, "# Run: go run ./cmd/gen-snapclient\n")
	fmt.Fprintf(&sb, "# Variant: %s\n\n", variantName)
	sb.WriteString(base)
	fmt.Fprintf(&sb, "\n# %s\n", h.comment)
	sb.WriteString(strings.Join(h.i2sPins, "\n") + "\n")
	sb.WriteString("\n# ")
	sb.WriteString(d.comment)
	sb.WriteString("\n")
	sb.WriteString(d.config)

	if p.enabled {
		fmt.Fprintf(&sb, "CONFIG_SNAPCLIENT_OTA_PULL_URL=\"%s/snapclient-%s/ota-manifest.json\"\n",
			pagesBase, variantName)
	} else {
		sb.WriteString("\n# OTA pull disabled — reduces firmware size\n")
		sb.WriteString("CONFIG_SNAPCLIENT_WEB_OTA_PULL=n\n")
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

	for _, h := range hardwares {
		for _, d := range discoveries {
			for _, p := range otaPullModes {
				variantName := variantNameFor(h, d, p)
				filename := "sdkconfig." + variantName
				fmt.Println(filename)
				if *dryRun {
					continue
				}
				path := filepath.Join(*dir, filename)
				if err := os.WriteFile(path, []byte(generate(h, d, p)), 0644); err != nil {
					fmt.Fprintf(os.Stderr, "error writing %s: %v\n", path, err)
					os.Exit(1)
				}
			}
		}
	}
}
