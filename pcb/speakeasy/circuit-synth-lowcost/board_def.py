"""Speakeasy Board — ESP32-S3 SUPER MINI + MAX98357A I2S Amplifier Module

Custom speaker board for Music Assistant / Sendspin integration.
"""

from board_helpers import component_from_lcsc, connect
from circuit_synth import Component, Net, circuit


@circuit(name="Speakeasy Lowcost")
def speakeasy_board():

    # ── Connectors ─────────────────────────────────────────────────────────

    # M3 plated through-hole mounting holes (3.2mm drill, copper-ringed, tied to GND)
    _mh_fp = "MountingHole:MountingHole_3.2mm_M3_Pad_Via"
    mh1 = Component(
        symbol="Mechanical:MountingHole_Pad",
        ref="H1",
        value="MountingHole",
        footprint=_mh_fp,
    )
    mh2 = Component(
        symbol="Mechanical:MountingHole_Pad",
        ref="H2",
        value="MountingHole",
        footprint=_mh_fp,
    )
    mh3 = Component(
        symbol="Mechanical:MountingHole_Pad",
        ref="H3",
        value="MountingHole",
        footprint=_mh_fp,
    )
    mh4 = Component(
        symbol="Mechanical:MountingHole_Pad",
        ref="H4",
        value="MountingHole",
        footprint=_mh_fp,
    )

    # ── Modules / ICs ──────────────────────────────────────────────────────

    esp32 = Component(
        symbol="ESP32_S3_SUPER_MINI_MODULE:ESP32_S3_SUPER_MINI_MODULE",
        ref="U1",
        footprint="Project:ESP32_S3_SUPER_MINI_MODULE",
    )

    # adafruit-MAX98357: mono I2S input → Class D amplifier, 2.5–5.5V, up to 3.2W/4Ω
    dac = Component(
        symbol="adafruit-MAX98357:adafruit-MAX98357",
        ref="U2",
        footprint="Project:adafruit-MAX98357",
    )

    # ── Nets ───────────────────────────────────────────────────────────────

    v5v = Net("+5V")
    v33v = Net("+3.3V")
    gnd = Net("GND")

    i2s_bclk = Net("I2S_BCLK")
    i2s_lrclk = Net("I2S_LRCLK")
    i2s_dout = Net("I2S_DOUT")

    # ── ESP32-S3 SUPER MINI ────────────────────────────────────────────────

    connect(esp32, "5V", v5v)
    connect(esp32, "GND", gnd)
    connect(esp32, "3.3V", v33v)

    # I2S → MAX98357A (safe GPIOs: IO16, IO17, IO18)
    # IO16 = BCLK    (bit clock)
    # IO17 = LRCLK   (left/right clock)
    # IO18 = DIN     (I2S data out from ESP)
    esp32["GPIO4"] += i2s_lrclk
    esp32["GPIO5"] += i2s_bclk
    esp32["GPIO6"] += i2s_dout

    # ── MAX98357A ──────────────────────────────────────────────────────────

    # Power: 5V in, GND, thermal EP to GND
    connect(dac, "Vin", v5v)
    connect(dac, "GND", gnd)

    # I2S bus
    dac["BCLK"] += i2s_bclk
    dac["LRC"] += i2s_lrclk
    dac["DIN"] += i2s_dout

    mh1[1] += gnd
    mh2[1] += gnd
    mh3[1] += gnd
    mh4[1] += gnd
