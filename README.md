# Speakeasy

ESPHome firmware for a custom ESP32-S3 Bluetooth/WiFi speaker that integrates with [Music Assistant](https://music-assistant.io/) via the [Sendspin](https://github.com/pavlonn/sendspin-cpp) protocol or [Snapcast](https://github.com/badaix/snapcast) for synchronized multi-room audio.

## Web Installer

Flash firmware directly from your browser (Chrome or Edge required) at the GitHub Pages site for this repo.

## Firmware Variants

| Variant | Protocol | Notes |
|---------|----------|-------|
| Sendspin | Sendspin | Music Assistant integration |
| Sendspin No BT | Sendspin | Bluetooth disabled (frees memory) |
| Snapcast | Snapcast | Static server IP in config |
| Snapcast No BT | Snapcast | Bluetooth disabled |
| Snapcast mDNS | Snapcast | Server discovered via mDNS |
| Snapcast mDNS No BT | Snapcast | mDNS + Bluetooth disabled |

## Hardware

| Component | Detail |
|-----------|--------|
| Board | ESP32-S3 Supermini (`ESP32-S3FH4R2`) — 4MB flash, 2MB quad PSRAM |
| DAC | External I2S DAC — DOUT: GPIO4, BCLK: GPIO5, LRCLK: GPIO6 |
| Audio | Mono, 48kHz FLAC |

## Architecture

```
Music Assistant → Sendspin → ESP32 WebSocket → sendspin_media_source → speaker_source → I2S DAC
```

Two media player entities are exposed to Home Assistant:

- **Sendspin Group Media Player** — the group player Music Assistant controls for synchronized playback
- **Media Player** — drives the actual I2S audio output

## Usage

```bash
# Validate config without building
esphome config speakeasy-sendspin.yaml

# Compile firmware
esphome compile speakeasy-sendspin.yaml

# Flash over USB
esphome upload speakeasy-sendspin.yaml

# Flash OTA
esphome upload speakeasy-sendspin.yaml --device <ip>

# Stream logs
esphome logs speakeasy-sendspin.yaml --device <ip>
```

## Configuration

Edit the substitutions at the top of the chosen variant YAML. For Snapcast variants, set the server address:

```yaml
substitutions:
  snapcast_server_ip: "192.168.1.1"
  snapcast_server_port: "1704"
```

### WiFi TX Power

`wifi_output_power` defaults to `8.5` dBm. The compact PCB antenna on the ESP32-S3 Supermini self-interferes at higher power, causing Sendspin time sync failures. A Home Assistant number entity (`WiFi TX Power`) is exposed to adjust this at runtime — the firmware will automatically step power up in 0.25 dBm increments (capped at 8.5 dBm) if WiFi drops, allowing recovery from weak-signal situations without permanently raising the baseline.

## FAQ

**Audio keeps cutting out with brief snippets then reconnecting.**

Sendspin time sync is failing. Check logs for `Time message X/8 timed out`. Known causes on this hardware:

- WiFi TX power too high — lower `wifi_output_power` toward `8.5` dBm
- WiFi power saving enabled — ensure `power_save_mode: none`
