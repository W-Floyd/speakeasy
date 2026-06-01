"""Speakeasy Board — ESP32-S3-MINI-1 + dual MAX98357A I2S Amplifiers

Custom speaker board for Music Assistant / Sendspin integration.

Design notes:
- ESP32-S3-MINI-1U-N4R2: 4MB flash, 2MB quad PSRAM; U.FL external antenna connector
- MAX98357A runs from VBUS (5V) for up to 3.2W output; 3dB more headroom than 3.3V
- MPM3810GQB-33-Z (QFN-12 3×2.5mm) provides +3.3V/1A for the ESP32 module only
- J1 is a 6-pin JST PH 2.0mm SMD header (C64659) for a panel-mount USB-C cable:
    pin 1: GND   pin 2: D+   pin 3: D-   pin 4: CC2   pin 5: CC1   pin 6: VCC
- CC resistors (5.1k to GND) on PCB side identify board as 5V power sink
- ESP32-S3 native USB used for programming — no USB-Serial bridge needed:
    IO19 (USB D-) → panel connector D-    IO20 (USB D+) → panel connector D+
- I2S pin assignment matches speakeasy firmware (both DACs share the I2S bus):
    IO4 → MAX98357A DIN     (I2S data out from ESP)
    IO5 → MAX98357A BCLK    (bit clock)
    IO6 → MAX98357A LRCLK   (left/right clock)
- U2 (DAC) SD_MODE controlled by 2-GPIO resistor network (IO7/IO8):
    IO7 Hi-Z,  IO8 Hi-Z  → Right channel
    IO7 Hi-Z,  IO8 HIGH  → Left channel   (default for Sendspin mono)
    IO7 HIGH,  IO8 Hi-Z  → Stereo (L+R)/2
    IO7 LOW,   IO8 Hi-Z  → Shutdown
- MAX98357A OUTP/OUTN connect directly to the speaker terminal (no DC-blocking cap;
  the MAX98357A is a filterless Class D amp with no DC offset on the outputs)
- J2 is the 2-pin SMD screw terminal for the speaker
"""

from circuit_synth import Component, Net, circuit
from board_helpers import component_from_lcsc, connect


@circuit(name="Speakeasy")
def speakeasy_board():

    # ── Modules / ICs ──────────────────────────────────────────────────────

    esp32 = component_from_lcsc("C22356044", ref="U1")

    # MAX98357AETE+T: mono I2S input → Class D amplifier, 2.5–5.5V, up to 3.2W/4Ω
    dac = component_from_lcsc("C910544", ref="U2")

    # MPM3810GQB-33-Z: integrated buck module, VBUS (5V) → 3.3V/1A for ESP32 module
    ldo = component_from_lcsc("C6909495", ref="U3")

    # ── Connectors ─────────────────────────────────────────────────────────

    # 6-pin JST PH 2.0mm SMD (mates with panel-mount USB-C cable, female PH)
    # Pinout: 1=GND  2=D+  3=D-  4=CC2  5=CC1  6=VCC  7/8=mounting tabs
    usbc = component_from_lcsc("C64659", ref="J1")

    # 2-pin SMD screw terminal for speaker 1 (DAC1 / U2)
    spkr_conn = component_from_lcsc("C20608465", ref="J2")

    # M3 plated through-hole mounting holes (3.2mm drill, copper-ringed, tied to GND)
    _mh_fp = "MountingHole:MountingHole_3.2mm_M3_Pad_Via"
    mh1 = Component(symbol="Mechanical:MountingHole_Pad", ref="H1", value="MountingHole", footprint=_mh_fp)
    mh2 = Component(symbol="Mechanical:MountingHole_Pad", ref="H2", value="MountingHole", footprint=_mh_fp)
    mh3 = Component(symbol="Mechanical:MountingHole_Pad", ref="H3", value="MountingHole", footprint=_mh_fp)
    mh4 = Component(symbol="Mechanical:MountingHole_Pad", ref="H4", value="MountingHole", footprint=_mh_fp)

    # UART test pads — probe points for 3V3, GND, TXD0, RXD0
    _tp_fp = "TestPoint:TestPoint_Pad_D1.5mm"
    tp_3v3 = Component(symbol="Connector:TestPoint", ref="TP1", value="3V3",  footprint=_tp_fp)
    tp_gnd = Component(symbol="Connector:TestPoint", ref="TP2", value="GND",  footprint=_tp_fp)
    tp_tx  = Component(symbol="Connector:TestPoint", ref="TP3", value="TXD0", footprint=_tp_fp)
    tp_rx  = Component(symbol="Connector:TestPoint", ref="TP4", value="RXD0", footprint=_tp_fp)

    # ── Passive components ─────────────────────────────────────────────────

    # CC1/CC2 pull-down resistors — 5.1k to GND, identifies board as 5V/900mA sink
    r_cc1 = component_from_lcsc("C25905", ref="R1", value="5.1k")
    r_cc2 = component_from_lcsc("C25905", ref="R2", value="5.1k")

    # EN pullup — supplements ESP32 module internal pullup for clean power-on reset
    r_en  = component_from_lcsc("C25744", ref="R3", value="10k")

    # MAX98357A SD_MODE 2-resistor GPIO network for runtime L/R/Stereo/Shutdown:
    #   IO7 (GPIO_A) → 1kΩ  → SD_MODE  (low-Z drive:  Stereo when HIGH, Shutdown when LOW)
    #   IO8 (GPIO_B) → 100kΩ → SD_MODE (mid-Z drive:  Left when HIGH)
    #   Both Hi-Z → SD_MODE floating → Right channel
    r_sd_a = component_from_lcsc("C11702", ref="R4", value="1k")
    r_sd_b = component_from_lcsc("C25741", ref="R5", value="100k")

    # LDO input bulk cap (+5V rail, near U3 input)
    c_ldo_in   = component_from_lcsc("C19702", ref="C1", value="10uF")

    # LDO output cap (+3.3V rail — required for AMS1117 stability: min 10uF)
    c_ldo_out  = component_from_lcsc("C15525", ref="C2", value="10uF")

    # ESP32 +3.3V high-frequency bypass
    c_esp_bypass = component_from_lcsc("C1525", ref="C3", value="100nF")

    # MAX98357A VDD bulk decoupling (+5V rail, near U2)
    c_dac_bulk   = component_from_lcsc("C52923", ref="C5", value="1uF")

    # MAX98357A VDD high-frequency bypass (as close to chip as possible)
    c_dac_bypass = component_from_lcsc("C1525", ref="C6", value="100nF")

    # Boot button: pulls IO0 low to enter USB download mode
    boot_btn = component_from_lcsc("C720477", ref="SW1", value="BOOT")

    # Reset button: pulls EN low to reset the ESP32
    rst_btn  = component_from_lcsc("C720477", ref="SW2", value="RST")

    # ── Nets ───────────────────────────────────────────────────────────────

    vbus    = Net("+5V")    # 5V from panel-mount USB-C
    vcc_3v3 = Net("+3.3V") # 3.3V regulated (ESP32 supply)
    gnd     = Net("GND")

    usb_dp  = Net("USB_DP")    # USB D+  → ESP32 USB_D+
    usb_dm  = Net("USB_DM")    # USB D-  → ESP32 USB_D-

    cc1 = Net("CC1")
    cc2 = Net("CC2")

    i2s_bclk  = Net("I2S_BCLK")   # IO5
    i2s_lrclk = Net("I2S_LRCLK")  # IO6
    i2s_dout  = Net("I2S_DOUT")   # IO4

    en_net    = Net("EN")
    gpio0     = Net("GPIO0")
    sd_mode   = Net("SD_MODE")
    sd_ctrl_a = Net("SD_CTRL_A")   # IO7 → 1kΩ → SD_MODE (Stereo/Shutdown)
    sd_ctrl_b = Net("SD_CTRL_B")   # IO8 → 100kΩ → SD_MODE (Left)
    uart_tx   = Net("UART_TX")     # ESP TXD0 → dongle RX
    uart_rx   = Net("UART_RX")     # ESP RXD0 ← dongle TX

    spkr_p = Net("SPKR_P")
    spkr_n = Net("SPKR_N")

    # ── JST-XH 6-pin (panel-mount USB-C interface) ─────────────────────────
    # Pin 1=GND  2=D+  3=D-  4=CC2  5=CC1  6=VCC

    usbc[1] += gnd
    usbc[2] += usb_dp
    usbc[3] += usb_dm
    usbc[4] += cc2
    usbc[5] += cc1
    usbc[6] += vbus
    usbc[7] += gnd  # SMD mounting tab
    usbc[8] += gnd  # SMD mounting tab

    # CC pull-downs on PCB side: identifies board as USB power sink
    r_cc1[1] += cc1
    r_cc1[2] += gnd
    r_cc2[1] += cc2
    r_cc2[2] += gnd

    # ── LDO: VBUS → 3.3V ──────────────────────────────────────────────────

    connect(ldo, "VIN",   vbus)
    connect(ldo, "OUT",   vcc_3v3)
    connect(ldo, "OUT_S", vcc_3v3)
    connect(ldo, "EN",    vbus)
    connect(ldo, "PGND",  gnd)
    connect(ldo, "AGND",  gnd)

    c_ldo_in[1]  += vbus
    c_ldo_in[2]  += gnd
    c_ldo_out[1] += vcc_3v3
    c_ldo_out[2] += gnd

    # ── ESP32-S3-WROOM-1 ──────────────────────────────────────────────────

    connect(esp32, "3V3", vcc_3v3)
    connect(esp32, "GND", gnd)
    esp32["EN"]     += en_net

    # Native USB peripheral (no CH340/CP2102 needed)
    # ESP32-S3 MINI: IO20 = USB D+, IO19 = USB D-
    esp32["IO20"] += usb_dp
    esp32["IO19"] += usb_dm

    # I2S → MAX98357A (must match speakeasy.yaml GPIO assignments)
    esp32["IO4"] += i2s_dout
    esp32["IO5"] += i2s_bclk
    esp32["IO6"] += i2s_lrclk

    # Boot/reset pins
    esp32["IO0"] += gpio0

    # SD_MODE channel select (see r_sd_a / r_sd_b for truth table)
    esp32["IO7"] += sd_ctrl_a
    esp32["IO8"] += sd_ctrl_b

    # UART0 → debug header
    esp32["TXD0"] += uart_tx
    esp32["RXD0"] += uart_rx

    # Decoupling
    c_esp_bypass[1] += vcc_3v3
    c_esp_bypass[2] += gnd

    # Reset circuit: pullup + momentary button to GND
    r_en[1]    += vcc_3v3
    r_en[2]    += en_net
    rst_btn[1] += en_net
    rst_btn[2] += gnd

    # Boot circuit: button pulls IO0 to GND (hold at power-on → download mode)
    boot_btn[1] += gpio0
    boot_btn[2] += gnd

    # ── MAX98357A ──────────────────────────────────────────────────────────

    dac["VDD"]          += vbus      # +5V → up to 3.2W into 4Ω load
    dac["GND"]          += gnd
    dac["EP"]           += gnd       # exposed thermal pad
    dac["BCLK"]         += i2s_bclk
    dac["LRCLK"]        += i2s_lrclk
    dac["DIN"]          += i2s_dout
    dac["~{SD_MODE}"]   += sd_mode   # pin 4; pulled high → left-channel/enable
    dac["OUTP"]         += spkr_p
    dac["OUTN"]         += spkr_n

    # SD_MODE GPIO control network (see component declaration for truth table)
    r_sd_a[1] += sd_ctrl_a
    r_sd_a[2] += sd_mode
    r_sd_b[1] += sd_ctrl_b
    r_sd_b[2] += sd_mode

    # VDD decoupling (Class D switching; place these as close as possible)
    c_dac_bulk[1]   += vbus
    c_dac_bulk[2]   += gnd
    c_dac_bypass[1] += vbus
    c_dac_bypass[2] += gnd

    # ── Speaker connector ──────────────────────────────────────────────────

    spkr_conn[1] += spkr_p
    spkr_conn[2] += spkr_n

    # ── UART test pads ─────────────────────────────────────────────────────

    tp_3v3[1] += vcc_3v3
    tp_gnd[1] += gnd
    tp_tx[1]  += uart_tx
    tp_rx[1]  += uart_rx

    mh1[1] += gnd
    mh2[1] += gnd
    mh3[1] += gnd
    mh4[1] += gnd