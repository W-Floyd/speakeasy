# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

ESPHome firmware for a custom ESP32-S3 Bluetooth/WiFi speaker ("Speakeasy") that integrates with Music Assistant via the Sendspin protocol for synchronized multi-room audio.

## Commands

```bash
# Validate config without building
esphome config speakeasy.yaml

# Compile firmware
esphome compile speakeasy.yaml

# Flash over USB
esphome upload speakeasy.yaml

# Flash OTA (device must be on network)
esphome upload speakeasy.yaml --device <ip>

# Stream logs
esphome logs speakeasy.yaml --device <ip>
```

## Hardware

**Board:** ESP32-S3 Supermini (`ESP32-S3FH4R2` — 4MB flash, 2MB quad PSRAM)  
**DAC:** External I2S DAC wired to GPIO4 (DOUT), GPIO5 (BCLK), GPIO6 (LRCLK)  
**Audio:** Mono output, 48kHz FLAC via Sendspin

Key hardware constraints:
- Chip is quad PSRAM only — do not change `psram.mode` to `octal`
- `output_power: 8.5` is intentional — compact PCB antenna self-interferes at full power, causing Sendspin time sync failures
- `power_save_mode: none` is required for Sendspin time burst round-trips to complete within timeout

## Architecture

Audio path: **Music Assistant → Sendspin protocol → ESP32 WebSocket server → `sendspin_media_source` → `speaker_source` media player → I2S DAC**

Two media player entities are exposed to Home Assistant:
- `sendspin_group_media_player` (platform: sendspin) — the group player MA controls for synchronized playback
- `external_media_player` (platform: speaker_source) — drives the actual I2S audio output

The `sendspin_media_source` bridges between them: Sendspin delivers audio into the source, the speaker_source player pulls from it and sends to the I2S speaker.

## Sendspin Notes

Sendspin uses a time burst protocol (8 round-trip messages) to synchronize clocks between MA and the ESP32. Failures appear as `sendspin.time_burst: Time message X/8 timed out` and cause `late binary: skipping N chunks` → brief audio snippets then reconnect.

Known causes of time burst timeouts on this hardware:
- WiFi power too high (fixed by `output_power: 8.5`)
- WiFi power saving adding latency (fixed by `power_save_mode: none`)
- The WiFi IRAM sdkconfig options (`CONFIG_ESP_WIFI_RX_IRAM_OPT` etc.) are **counterproductive on ESP32-S3** — the S3 maps WiFi code to IRAM by default

Sendspin component version in use: `sendspin-cpp v0.6.1`

## Versioning

The project version is set in `common/base.yaml` under `esphome.project.version`. Bump it manually as an integer (`"1"`, `"2"`, …) when making a release — it appears in Home Assistant's device info.

```bash
# Bump version
sed -i 's/version: "[0-9]*"/version: "2"/' common/base.yaml
```

## Reference Files

- `example.yaml` — original reference config this firmware was derived from
- `example2.yaml` — HA Voice PE reference config (used for audio pipeline patterns)
