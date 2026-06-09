Ready-made ESP32-S3 multi-room audio hardware and firmware.

---

## Low Cost (off-the-shelf only)

A ~$30 per-room speaker using off-the-shelf modules and no soldering beyond wire terminals.

### Parts

| Part | Qty | Price | Link |
|------|-----|-------|------|
| ESP32-S3 Supermini | 1 | ~$4.25 | [Amazon B0GS283V6F](https://amazon.com/dp/B0GS283V6F) |
| MAX98357A I2S amplifier breakout | 1 | ~$2.00 | [Amazon B0B4GK5R1R](https://amazon.com/dp/B0B4GK5R1R) |
| Saiyin 3" wall-mount passive speaker | 1 | ~$18.00 | [Amazon B0DGLMY9SB](https://amazon.com/dp/B0DGLMY9SB) |
| Dupont jumper wires F-F (recommend 10 cm) | 5 | <$1.00 | [Amazon B07GD312VG](https://www.amazon.com/dp/B07GD312VG) |
| USB-C power supply + cable | 1 | ~$4.50 | [Amazon B08G4GRQYV](https://www.amazon.com/dp/B08G4GRQYV) |
| **Total** | | **~$29.75** | |

### Wiring

| MAX98357A pin | ESP32-S3 Supermini pin |
|---------------|------------------------|
| BCLK          | GPIO 11                |
| LRC           | GPIO 10                |
| DIN           | GPIO 12                |
| VIN           | 5V                     |
| GND           | GND                    |
| Speaker+/−    | Speaker terminals      |

### Setup

1. Wire the MAX98357A to the ESP32-S3 Supermini as above.
2. Connect the speaker to the MAX98357A output terminals.
3. Plug the ESP32-S3 into USB and flash firmware from the **Flash** tab.
4. Provision WiFi credentials via [Improv Serial](https://www.improv-wifi.com/serial/) (USB, all builds) or Improv BLE (requires a Bluetooth-enabled build).
5. Add the device to Music Assistant or your Snapcast server.
