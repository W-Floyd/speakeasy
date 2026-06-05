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
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_QUAD=y
CONFIG_SPIRAM_BOOT_INIT=y
CONFIG_SPIRAM_USE_MALLOC=y
CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL=16384
CONFIG_ESP32S3_DEFAULT_CPU_FREQ_240=y
CONFIG_ESP32S3_DATA_CACHE_64KB=y
CONFIG_ESP32S3_DATA_CACHE_LINE_64B=y
CONFIG_ESP32S3_INSTRUCTION_CACHE_32KB=y
CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP=y
CONFIG_ESP32_WIFI_STATIC_RX_BUFFER_NUM=16
CONFIG_ESP32_WIFI_DYNAMIC_RX_BUFFER_NUM=64
CONFIG_ESP_WIFI_STATIC_TX_BUFFER_NUM=16
CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM=32
CONFIG_ESP_WIFI_MGMT_SBUF_NUM=32
CONFIG_ESPTOOLPY_FLASHMODE_QIO=y
CONFIG_ESPTOOLPY_FLASHFREQ_80M=y
# Compiler: optimize for performance (O2) over size.
CONFIG_COMPILER_OPTIMIZATION_PERF=y
# FreeRTOS: keep scheduler in IRAM for fast context switches; 1ms tick resolution.
CONFIG_FREERTOS_PLACE_FUNCTIONS_INTO_FLASH=n
CONFIG_FREERTOS_HZ=1000
CONFIG_FREERTOS_IDLE_TASK_STACKSIZE=1536
CONFIG_ESP_WIFI_IRAM_OPT=y
CONFIG_ESP_WIFI_RX_IRAM_OPT=y
# AMPDU block-acknowledgment windows for better WiFi streaming throughput.
CONFIG_ESP_WIFI_TX_BA_WIN=8
CONFIG_ESP_WIFI_RX_BA_WIN=16
# WiFi provisioning via Improv serial — configure credentials at https://web.esphome.io/
CONFIG_ENABLE_WIFI_PROVISIONING=y
# Light sleep gates USB clocks on ESP32-S3, breaking USB Serial JTAG used by Improv.
CONFIG_PM_ENABLE=n
# Prevent power save mode from activating on WiFi disconnect (avoids reconnect latency spike).
CONFIG_ESP_WIFI_STA_DISCONNECTED_PM_ENABLE=n
# Pin LwIP/TCP to core 0 alongside WiFi, freeing core 1 for audio.
CONFIG_LWIP_TCPIP_TASK_AFFINITY_CPU0=y
# LWIP TCP — larger windows, selective ACK, and buffers improve streaming smoothness.
CONFIG_LWIP_TCP_SND_BUF_DEFAULT=11520
CONFIG_LWIP_TCP_WND_DEFAULT=11520
CONFIG_LWIP_TCP_RECVMBOX_SIZE=16
CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=64
CONFIG_LWIP_TCP_OOSEQ_MAX_PBUFS=8
CONFIG_LWIP_TCP_SACK_OUT=y
# Zero logging overhead at runtime; level can be raised at runtime for debugging.
CONFIG_LOG_DEFAULT_LEVEL_NONE=y
CONFIG_LOG_MAXIMUM_LEVEL_INFO=y
# MAX98357A has no hardware volume control — use DSP-based software volume.
CONFIG_USE_DSP_PROCESSOR=y
CONFIG_SNAPCLIENT_USE_SOFT_VOL=y
`

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

func generate(d discovery) string {
	var sb strings.Builder
	fmt.Fprintf(&sb, "# Generated from cmd/gen-snapclient — do not edit directly.\n")
	fmt.Fprintf(&sb, "# Run: go run ./cmd/gen-snapclient\n")
	fmt.Fprintf(&sb, "# Variant: %s\n\n", d.name)
	sb.WriteString(base)
	sb.WriteString("\n# ")
	sb.WriteString(d.comment)
	sb.WriteString("\n")
	sb.WriteString(d.config)
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
		filename := "sdkconfig." + d.name
		fmt.Println(filename)
		if *dryRun {
			continue
		}
		path := filepath.Join(*dir, filename)
		if err := os.WriteFile(path, []byte(generate(d)), 0644); err != nil {
			fmt.Fprintf(os.Stderr, "error writing %s: %v\n", path, err)
			os.Exit(1)
		}
	}
}
