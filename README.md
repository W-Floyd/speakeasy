# Speakeasy

ESPHome firmware for a custom ESP32-S3 WiFi speaker that integrates with [Music Assistant](https://music-assistant.io/) via the [Sendspin](https://github.com/pavlonn/sendspin-cpp) protocol or [Snapcast](https://github.com/badaix/snapcast) for synchronized multi-room audio.

## Web Installer

Flash firmware directly from your browser at **https://w-floyd.github.io/speakeasy/**. Requires Chrome or Edge, or Firefox with the [WebSerial extension](https://addons.mozilla.org/en-US/firefox/addon/webserial-for-firefox/).

The installer lets you pick your configuration interactively: protocol, server discovery, Bluetooth, IPv6, and WiFi TX power.

## Firmware Variants

Two protocol stacks are available. Both Snapcast variants use [CarlosDerSeher/snapclient](https://github.com/CarlosDerSeher/snapclient) under the hood — the difference is the surrounding framework:

| Protocol | Discovery | Notes |
|----------|-----------|-------|
| Sendspin | mDNS | Native Music Assistant integration |
| Snapcast (ESPHome) | mDNS or static IP | snapclient wrapped in ESPHome — Home Assistant integration |
| Snapcast (standalone) | mDNS or manual IP | snapclient running bare ESP-IDF — no ESPHome/HA |

Each variant is further configurable along these axes (ESPHome builds):

- **Bluetooth** — BLE for WiFi provisioning via Improv; disable once set up to free ~100 KB RAM
- **IPv6** — dual-stack networking
- **WiFi TX power** — stock, 9 dBm fixed, stock+ramp, or 9 dBm+ramp

## Hardware

| Component | Detail |
|-----------|--------|
| Board | ESP32-S3 Supermini (`ESP32-S3FH4R2`) — 4MB flash, 2MB quad PSRAM |
| DAC + Amplifier | MAX98357A I2S DAC + Class D amplifier — LRCLK: GPIO10, BCLK: GPIO11, DOUT: GPIO12 |

## Architecture

**Sendspin:**
```
Music Assistant → Sendspin → ESP32 WebSocket → sendspin_media_source → speaker_source → I2S DAC
```

Two Home Assistant entities: `sendspin_group_media_player` (what MA controls) and the speaker_source player (drives I2S output).

**Snapcast (ESPHome and standalone):**
```
Snapcast server → CarlosDerSeher/snapclient → I2S DAC
```

ESPHome builds wrap snapclient as a media player entity exposed to Home Assistant. Standalone builds run snapclient directly on bare ESP-IDF with no ESPHome or HA integration.

## Usage

```bash
# Validate config without building
esphome config speakeasy-ss-mdns.yaml

# Compile firmware
esphome compile speakeasy-ss-mdns.yaml

# Flash over USB
esphome upload speakeasy-ss-mdns.yaml

# Flash OTA
esphome upload speakeasy-ss-mdns.yaml --device <ip>

# Stream logs
esphome logs speakeasy-ss-mdns.yaml --device <ip>
```

YAML filenames follow the pattern `speakeasy-{protocol}-{options}.yaml`. Protocol is `ss` (Sendspin) or `sc` (Snapcast). Options are `mdns`, `bt` (Bluetooth), `6` (IPv6), and WiFi power (`w9`, `wr`, `w9r`).

## Configuration

Edit the substitutions at the top of the chosen variant YAML. For Snapcast variants with a static server address:

```yaml
substitutions:
  snapcast_server_ip: "192.168.1.1"
  snapcast_server_port: "1704"
```

### WiFi TX Power

The compact PCB antenna on the ESP32-S3 Supermini self-interferes at high TX power, causing Sendspin time sync failures. `8.5` dBm is the recommended cap. Ramp variants expose a Home Assistant number entity (`WiFi TX Power`) and automatically step power up in 0.25 dBm increments if WiFi drops, allowing recovery from weak-signal situations without raising the baseline permanently.

### Standalone Snapcast

Standalone builds are configured via kconfig defaults in `snapclient-kconfig/`. The `manual` variant requires editing `CONFIG_SNAPSERVER_HOST` in `snapclient-kconfig/sdkconfig.manual` before building.

## FAQ

**Audio keeps cutting out with brief snippets then reconnecting.**

Sendspin time sync is failing. Check logs for `Time message X/8 timed out`. Known causes on this hardware:

- WiFi TX power too high — lower toward `8.5` dBm
- WiFi power saving enabled — ensure `power_save_mode: none`
