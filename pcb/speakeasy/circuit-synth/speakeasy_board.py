"""Speakeasy Board — ESP32-S3-MINI-1 + dual MAX98357A I2S Amplifiers

Custom speaker board for Music Assistant / Sendspin integration.

Design notes:
- ESP32-S3-MINI-1U-N4R2: 4MB flash, 2MB quad PSRAM; U.FL external antenna connector
- MAX98357A runs from VBUS (5V) for up to 3.2W output; 3dB more headroom than 3.3V
- AMS1117-3.3 (SOT-223) provides +3.3V/800mA for the ESP32 module only
- J1 is a 6-pin JST PH 2.0mm SMD header (C64659) for a panel-mount USB-C cable:
    pin 1: GND   pin 2: D+   pin 3: D-   pin 4: CC2   pin 5: CC1   pin 6: VCC
- CC resistors (5.1k to GND) on PCB side identify board as 5V power sink
- ESP32-S3 native USB used for programming — no USB-Serial bridge needed:
    IO19 (USB D-) → panel connector D-    IO20 (USB D+) → panel connector D+
- I2S pin assignment matches speakeasy firmware (both DACs share the I2S bus):
    IO4 → MAX98357A DIN     (I2S data out from ESP)
    IO5 → MAX98357A BCLK    (bit clock)
    IO6 → MAX98357A LRCLK   (left/right clock)
- U2 (DAC1) SD_MODE controlled by 2-GPIO resistor network (IO7/IO8):
    IO7 Hi-Z,  IO8 Hi-Z  → Right channel
    IO7 Hi-Z,  IO8 HIGH  → Left channel   (default for Sendspin mono)
    IO7 HIGH,  IO8 Hi-Z  → Stereo (L+R)/2
    IO7 LOW,   IO8 Hi-Z  → Shutdown
- U4 (DAC2) SD_MODE controlled by mirrored 2-GPIO resistor network (IO9/IO10):
    IO9 Hi-Z,  IO10 Hi-Z  → Right channel
    IO9 Hi-Z,  IO10 HIGH  → Left channel
    IO9 HIGH,  IO10 Hi-Z  → Stereo (L+R)/2
    IO9 LOW,   IO10 Hi-Z  → Shutdown
- MAX98357A OUTP/OUTN connect directly to the speaker terminal (no DC-blocking cap;
  the MAX98357A is a filterless Class D amp with no DC offset on the outputs)
- J2 (speaker 1) and J3 (speaker 2) are independent 2-pin SMD screw terminals
"""

from circuit_synth import Component, Net, circuit
from lookup_part import lookup

# Populated by component_from_lcsc() as components are instantiated.
# Used by add_lcsc_numbers() to stamp LCSC properties onto the schematic.
_LCSC_REGISTRY: dict = {}


def component_from_lcsc(lcsc: str, ref: str, **overrides):
    """Create a Component, registering its LCSC number for BOM stamping.

    If symbol is not provided, looks it up from the local EasyEDA library and
    prefixes it with 'EasyEDA:'.  Pass symbol/footprint/value as keyword args
    to use standard KiCad library parts (e.g. Device:R) instead.
    """
    if "symbol" not in overrides:
        data = lookup(lcsc)
        if data is None:
            raise ValueError(f"LCSC {lcsc} not found in ~/KiCad/EasyEDA.kicad_sym — "
                             f"export it from EasyEDA first")
        overrides.setdefault("value", data.get("Value", ""))
        overrides.setdefault("footprint", data.get("Footprint", ""))
        overrides["symbol"] = f"EasyEDA:{data['symbol']}"
    _LCSC_REGISTRY[ref] = lcsc
    return Component(ref=ref, **overrides)


def connect(component, pin_name, net):
    """Connect all pins named pin_name to net.

    circuit-synth's component[name] only wires the first matching pin.
    This helper finds every pin with the given name (e.g. duplicate VOUT
    or GND pads) and connects them all, so nothing is silently left floating.
    """
    from circuit_synth.kicad.kicad_symbol_cache import SymbolLibCache
    import re as _re

    sym_data = SymbolLibCache.get_symbol_data(component.symbol)
    pins = sym_data.get("pins", {})

    # pins may be a dict keyed by number or a list — normalise to [(num, name)]
    if isinstance(pins, dict):
        items = [(num, info.get("name", "")) for num, info in pins.items()]
    else:
        items = [(p.get("number"), p.get("name", "")) for p in (pins or [])]

    matched = [num for num, name in items if name == pin_name]

    if not matched:
        # Fall back to direct connection (catches numeric pin refs)
        component[pin_name] += net
        return

    for num in matched:
        # circuit-synth uses integers for pin number access, strings for pin names
        try:
            component[int(num)] += net
        except (ValueError, TypeError, Exception):
            component[num] += net


@circuit(name="Speakeasy")
def speakeasy_board():

    # ── Modules / ICs ──────────────────────────────────────────────────────

    esp32 = component_from_lcsc("C22356044", ref="U1")

    # MAX98357AETE+T: mono I2S input → Class D amplifier, 2.5–5.5V, up to 3.2W/4Ω
    dac = component_from_lcsc("C910544", ref="U2")

    # Second MAX98357A — shares I2S bus, independent SD_MODE via IO9/IO10
    dac2 = component_from_lcsc("C910544", ref="U4")

    # AMS1117-3.3: 800mA LDO, VBUS (5V) → 3.3V for ESP32 module
    ldo = component_from_lcsc("C6186", ref="U3")

    # ── Connectors ─────────────────────────────────────────────────────────

    # 6-pin JST PH 2.0mm SMD (mates with panel-mount USB-C cable, female PH)
    # Pinout: 1=GND  2=D+  3=D-  4=CC2  5=CC1  6=VCC  7/8=mounting tabs
    usbc = component_from_lcsc("C64659", ref="J1")

    # 2-pin SMD screw terminal for speaker 1 (DAC1 / U2)
    spkr_conn = component_from_lcsc("C20608465", ref="J2")

    # 2-pin SMD screw terminal for speaker 2 (DAC2 / U4)
    spkr_conn2 = component_from_lcsc("C20608465", ref="J3")


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
    c_ldo_in   = component_from_lcsc("C15850", ref="C1", value="10uF")

    # LDO output cap (+3.3V rail — required for AMS1117 stability: min 10uF)
    c_ldo_out  = component_from_lcsc("C15850", ref="C2", value="10uF")

    # ESP32 +3.3V bulk decoupling
    c_esp_bulk = component_from_lcsc("C15850", ref="C3", value="10uF")

    # ESP32 +3.3V high-frequency bypass
    c_esp_bypass = component_from_lcsc("C14663", ref="C4", value="100nF")

    # MAX98357A VDD bulk decoupling (+5V rail, near U2)
    c_dac_bulk   = component_from_lcsc("C52923", ref="C5", value="1uF")

    # MAX98357A VDD high-frequency bypass (as close to chip as possible)
    c_dac_bypass = component_from_lcsc("C14663", ref="C6", value="100nF")

    # DAC2 (U4) VDD bulk decoupling
    c_dac2_bulk   = component_from_lcsc("C52923", ref="C7", value="1uF")

    # DAC2 (U4) VDD high-frequency bypass
    c_dac2_bypass = component_from_lcsc("C14663", ref="C8", value="100nF")

    # DAC2 SD_MODE GPIO control network (same topology as R4/R5, for IO9/IO10)
    r_sd2_a = component_from_lcsc("C11702", ref="R6", value="1k")
    r_sd2_b = component_from_lcsc("C25741", ref="R7", value="100k")

    # Boot button: pulls IO0 low to enter USB download mode
    # C318884 pin layout: A(1)+B(2) = one terminal, C(3)+D(4) = other terminal
    boot_btn = component_from_lcsc("C318884", ref="SW1", value="BOOT")

    # Reset button: pulls EN low to reset the ESP32
    rst_btn  = component_from_lcsc("C318884", ref="SW2", value="RST")

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

    sd_mode2   = Net("SD_MODE2")
    sd_ctrl2_a = Net("SD_CTRL2_A") # IO9  → 1kΩ  → SD_MODE2
    sd_ctrl2_b = Net("SD_CTRL2_B") # IO10 → 100kΩ → SD_MODE2

    spkr2_p = Net("SPKR2_P")
    spkr2_n = Net("SPKR2_N")

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

    connect(ldo, "VIN",  vbus)
    connect(ldo, "VOUT", vcc_3v3)
    connect(ldo, "GND",  gnd)

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
    c_esp_bulk[1]   += vcc_3v3
    c_esp_bulk[2]   += gnd
    c_esp_bypass[1] += vcc_3v3
    c_esp_bypass[2] += gnd

    # Reset circuit: pullup + momentary button to GND
    r_en[1]    += vcc_3v3
    r_en[2]    += en_net
    rst_btn[1] += en_net
    rst_btn[3] += gnd

    # Boot circuit: button pulls IO0 to GND (hold at power-on → download mode)
    boot_btn[1] += gpio0
    boot_btn[3] += gnd

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

    # ── MAX98357A (DAC2 / U4) ──────────────────────────────────────────────

    dac2["VDD"]          += vbus
    dac2["GND"]          += gnd
    dac2["EP"]           += gnd
    dac2["BCLK"]         += i2s_bclk
    dac2["LRCLK"]        += i2s_lrclk
    dac2["DIN"]          += i2s_dout
    dac2["~{SD_MODE}"]   += sd_mode2
    dac2["OUTP"]         += spkr2_p
    dac2["OUTN"]         += spkr2_n

    # SD_MODE2 GPIO control network (IO9/IO10, mirrors DAC1 R4/R5)
    r_sd2_a[1] += sd_ctrl2_a
    r_sd2_a[2] += sd_mode2
    r_sd2_b[1] += sd_ctrl2_b
    r_sd2_b[2] += sd_mode2

    # IO9/IO10 → DAC2 SD_MODE
    esp32["IO9"]  += sd_ctrl2_a
    esp32["IO10"] += sd_ctrl2_b

    # VDD decoupling for DAC2
    c_dac2_bulk[1]   += vbus
    c_dac2_bulk[2]   += gnd
    c_dac2_bypass[1] += vbus
    c_dac2_bypass[2] += gnd

    # ── Speaker connectors ─────────────────────────────────────────────────

    spkr_conn[1] += spkr_p
    spkr_conn[2] += spkr_n

    spkr_conn2[1] += spkr2_p
    spkr_conn2[2] += spkr2_n

    # ── UART test pads ─────────────────────────────────────────────────────

    tp_3v3[1] += vcc_3v3
    tp_gnd[1] += gnd
    tp_tx[1]  += uart_tx
    tp_rx[1]  += uart_rx


def fix_power_symbol_overlaps(sch_path):
    """Move GND power symbols that sit on VBUS symbols to the correct cap pin.

    circuit-synth places GND power symbols at the same coordinate as VBUS
    symbols (both end up at pin 2 / top of the decoupling cap).  The GND
    symbols should instead be at pin 1 / bottom of the cap.

    For Device:C in default orientation:
      pin 2 (top)    = (cx, cy - 3.81)  ← where VBUS is placed
      pin 1 (bottom) = (cx, cy + 3.81)  ← where GND belongs

    This finds caps whose bottom pin has no GND symbol and moves displaced
    GND symbols there, matching them by x-coordinate.
    """
    import kicad_sch_api as ksa

    sch = ksa.load_schematic(sch_path)
    POSITIVE_SYMBOLS = {"power:+5V", "power:+3.3V", "power:VBUS"}
    pwr = [c for c in sch.components if c.lib_id in POSITIVE_SYMBOLS | {"power:GND"}]

    PIN_OFFSET = 3.81  # Device:C pin-to-center distance (mm)

    vbus_xy = {(round(c.position.x, 2), round(c.position.y, 2))
               for c in pwr if c.lib_id in POSITIVE_SYMBOLS}
    gnd_xy  = {(round(c.position.x, 2), round(c.position.y, 2))
               for c in pwr if c.lib_id == "power:GND"}

    # Find caps whose bottom pin (cy + PIN_OFFSET) lacks a GND symbol.
    caps = [c for c in sch.components if c.lib_id == "Device:C"]
    unconnected_bottoms = []
    for cap in caps:
        cx = round(cap.position.x, 2)
        cy = round(cap.position.y, 2)
        bottom = (cx, round(cy + PIN_OFFSET, 2))
        if bottom not in gnd_xy:
            unconnected_bottoms.append(bottom)

    # Find GND symbols sitting on a VBUS position (misplaced).
    misplaced = [c for c in pwr
                 if c.lib_id == "power:GND"
                 and (round(c.position.x, 2), round(c.position.y, 2)) in vbus_xy]

    fixed = 0
    for gnd_sym in misplaced:
        if not unconnected_bottoms:
            break
        # Pick the bottom pin at the same x (same cap column).
        gx = round(gnd_sym.position.x, 2)
        target = next((b for b in unconnected_bottoms if b[0] == gx), None)
        if target is None:
            # Fall back to nearest by distance.
            gy = round(gnd_sym.position.y, 2)
            target = min(unconnected_bottoms, key=lambda b: (b[0]-gx)**2 + (b[1]-gy)**2)
        gnd_sym.move(target[0], target[1])
        unconnected_bottoms.remove(target)
        fixed += 1

    if fixed:
        sch.save(sch_path)
        print(f"Fixed {fixed} GND symbol(s) moved to cap bottom pin")


def add_lcsc_numbers(sch_path):
    """Stamp LCSC part numbers onto each component in the schematic."""
    import kicad_sch_api as ksa

    sch = ksa.load_schematic(sch_path)
    stamped = 0
    for comp in sch.components:
        lcsc = _LCSC_REGISTRY.get(comp.reference)
        if lcsc:
            comp.add_property("LCSC", lcsc)
            stamped += 1
    if stamped:
        sch.save(sch_path)
        print(f"Stamped LCSC numbers on {stamped} component(s)")


def preserve_component_uuids(old_sch_path, new_sch_path,
                             net_path=None, pro_path=None):
    """Re-apply stable UUIDs from the existing schematic to the newly generated one.

    circuit-synth assigns fresh UUIDs on every run, creating noisy diffs and breaking
    KiCad's schematic↔PCB links (net file tstamps are the same UUID values).

    Three things are stabilised:
    - Root sheet UUID — propagates into hierarchy_path, root_uuid, and path fields
    - Component instance UUIDs — only when lib_id is unchanged (swapped components get fresh UUIDs)
    - Per-pin UUIDs inside component blocks — stabilised alongside the component UUID
    """
    import re

    def get_root_uuid(text):
        m = re.search(r'^\s*\(uuid\s+"([^"]+)"', text, re.MULTILINE)
        return m.group(1) if m else None

    def extract_blocks(text):
        """Yield (ref, lib_id, uuid, pin_uuids, start, end) for every component instance."""
        for m in re.finditer(r'\(symbol\s+\(lib_id\s+"([^"]+)"\)', text):
            lib_id = m.group(1)
            start = m.start()
            depth, end = 0, start
            for i, ch in enumerate(text[start:], start):
                if ch == "(": depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            block = text[start:end]
            uuid_m = re.search(r'\(uuid\s+"([^"]+)"', block)
            ref_m  = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
            if not (uuid_m and ref_m):
                continue
            # Map pin number → uuid for all (pin "N" (uuid "...")) entries
            pin_uuids = {m2.group(1): m2.group(2)
                         for m2 in re.finditer(r'\(pin\s+"([^"]+)"\s*\(\s*uuid\s+"([^"]+)"', block)}
            yield ref_m.group(1), lib_id, uuid_m.group(1), pin_uuids, start, end

    try:
        old_text = open(old_sch_path).read()
    except FileNotFoundError:
        return

    old_root_uuid = get_root_uuid(old_text)
    old_map = {ref: (lib_id, uuid, pin_uuids)
               for ref, lib_id, uuid, pin_uuids, *_ in extract_blocks(old_text)}
    if not old_map and not old_root_uuid:
        return

    new_text = open(new_sch_path).read()

    # ── 1. Stabilise root sheet UUID ────────────────────────────────────────
    result = new_text
    if old_root_uuid:
        new_root_uuid = get_root_uuid(result)
        if new_root_uuid and new_root_uuid != old_root_uuid:
            result = result.replace(new_root_uuid, old_root_uuid)

    # ── 2. Stabilise hierarchical_label UUIDs (net name labels) ────────────
    def extract_label_uuids(text):
        """Return {(name, index): uuid} for hierarchical_label elements."""
        mapping = {}
        counts = {}
        for m in re.finditer(
            r'\(hierarchical_label\s+"([^"]+)".*?\(uuid\s+"([^"]+)"',
            text, re.DOTALL
        ):
            name = m.group(1)
            idx = counts.get(name, 0)
            mapping[(name, idx)] = m.group(2)
            counts[name] = idx + 1
        return mapping

    old_labels = extract_label_uuids(old_text)
    if old_labels:
        new_labels = extract_label_uuids(result)
        for key, new_uuid in new_labels.items():
            old_uuid = old_labels.get(key)
            if old_uuid and old_uuid != new_uuid:
                result = result.replace(f'"{new_uuid}"', f'"{old_uuid}"', 1)

    # ── 3. Stabilise component + pin UUIDs ─────────────────────────────────
    uuid_replacements = {}  # new_uuid → old_uuid, for patching net/pro files
    if new_root_uuid := get_root_uuid(new_text):
        if old_root_uuid and new_root_uuid != old_root_uuid:
            uuid_replacements[new_root_uuid] = old_root_uuid

    patched = []
    pos = 0
    preserved = replaced = 0
    for ref, lib_id, new_uuid, _new_pins, start, end in extract_blocks(result):
        patched.append(result[pos:start])
        block = result[start:end]
        old_entry = old_map.get(ref)
        if old_entry and old_entry[0] == lib_id:
            uuid_replacements[new_uuid] = old_entry[1]
            # Restore component UUID
            block = re.sub(r'(\(uuid\s+)"[^"]+"', rf'\1"{old_entry[1]}"', block, count=1)
            # Restore per-pin UUIDs
            old_pin_uuids = old_entry[2]
            def _restore_pin(m):
                pin_num = m.group(1)
                old_pu = old_pin_uuids.get(pin_num)
                if old_pu:
                    return f'(pin "{pin_num}"\n\t\t\t\t(uuid "{old_pu}"'
                return m.group(0)
            block = re.sub(r'\(pin\s+"([^"]+)"\s*\(\s*uuid\s+"[^"]+"', _restore_pin, block)
            preserved += 1
        else:
            replaced += 1
        patched.append(block)
        pos = end
    patched.append(result[pos:])
    result = "".join(patched)

    if result != new_text:
        open(new_sch_path, "w").write(result)
    print(f"UUIDs: {preserved} preserved (unchanged components), {replaced} refreshed (new/swapped)")

    # ── 4. Patch .kicad_pro with schematic UUID replacements ────────────────
    if pro_path:
        try:
            text = open(pro_path).read()
            patched_text = text
            for new_uuid, old_uuid in uuid_replacements.items():
                patched_text = patched_text.replace(new_uuid, old_uuid)
            if patched_text != text:
                open(pro_path, "w").write(patched_text)
        except FileNotFoundError:
            pass

    # ── 5. Patch net file tstamps by component ref ──────────────────────────
    # The net file uses its own tstamps independent of the schematic UUIDs.
    # Match old→new by ref name, then restore old tstamps.
    if net_path:
        UUID_RE = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

        def extract_net_tstamps(text):
            """Return {ref: tstamp} from a KiCad net file.
            Matches the UUID-shaped tstamp at the end of each comp block,
            not the sheetpath's (tstamps "/") placeholder.
            """
            mapping = {}
            for m in re.finditer(
                rf'\(comp\s+\(ref\s+"([^"]+)"\).*?\(tstamps\s+"({UUID_RE})"\)',
                text, re.DOTALL
            ):
                mapping[m.group(1)] = m.group(2)
            return mapping

        def extract_net_sheet_tstamp(text):
            m = re.search(rf'\(sheet\b.*?\(tstamps\s+"(/({UUID_RE})/)"\)', text, re.DOTALL)
            return m.group(2) if m else None

        import pathlib as _pl
        old_net_path = _pl.Path(old_sch_path).parent / _pl.Path(net_path).name
        try:
            old_net = old_net_path.read_text()
        except FileNotFoundError:
            old_net = None

        if old_net:
            try:
                new_net = open(net_path).read()
            except FileNotFoundError:
                new_net = None

            if new_net:
                # Stabilise the generated date so it doesn't appear in every diff
                new_net = re.sub(r'\(date "[^"]*"\)', '(date "1970-01-01T00:00:00+0000")', new_net)
                open(net_path, "w").write(new_net)
                old_net_tstamps = extract_net_tstamps(old_net)
                new_net_tstamps = extract_net_tstamps(new_net)

                result_net = new_net
                # Restore per-component tstamps
                for ref, new_ts in new_net_tstamps.items():
                    old_ts = old_net_tstamps.get(ref)
                    if old_ts and old_ts != new_ts:
                        result_net = result_net.replace(
                            f'(tstamps "{new_ts}")', f'(tstamps "{old_ts}")', 1
                        )

                # Restore sheet tstamp (root UUID in net file)
                old_sheet_ts = extract_net_sheet_tstamp(old_net)
                new_sheet_ts = extract_net_sheet_tstamp(new_net)
                if old_sheet_ts and new_sheet_ts and old_sheet_ts != new_sheet_ts:
                    result_net = result_net.replace(
                        f'"/{new_sheet_ts}/"', f'"/{old_sheet_ts}/"'
                    )

                if result_net != new_net:
                    open(net_path, "w").write(result_net)


def write_jlcpcb_bom(sch_path, out_path):
    """Write a JLCPCB-compatible BOM CSV from the schematic."""
    import kicad_sch_api as ksa
    import csv
    from collections import defaultdict

    sch = ksa.load_schematic(sch_path)
    # Skip power symbols and virtual refs
    rows = []
    for comp in sch.components:
        ref = comp.reference
        if not ref or ref.startswith("#"):
            continue
        lcsc = _LCSC_REGISTRY.get(ref, "")
        value = comp.value or ""
        fp = comp.footprint or ""
        rows.append((ref, value, fp, lcsc))

    # Group identical (value, footprint, lcsc) lines, combine designators
    groups = defaultdict(list)
    for ref, value, fp, lcsc in rows:
        groups[(value, fp, lcsc)].append(ref)

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for (value, fp, lcsc), refs in sorted(groups.items()):
            w.writerow([value, ",".join(sorted(refs)), fp, lcsc])

    print(f"JLCPCB BOM: {out_path}")


if __name__ == "__main__":
    import os, shutil, pathlib, sys

    # Verify we're running the local circuit-synth fork, not a stale installed copy.
    import circuit_synth as _cs
    _cs_path = pathlib.Path(_cs.__file__).resolve()
    _fork = (pathlib.Path(__file__).resolve().parent.parent.parent
             / "circuit-synth-local" / "src" / "circuit_synth").resolve()
    if not str(_cs_path).startswith(str(_fork)):
        print(f"ERROR: circuit_synth loaded from wrong location:\n  {_cs_path}\n"
              f"Expected: {_fork}\n\n"
              f"Fix with:\n  uv pip install setuptools && "
              f"uv pip install --editable ../circuit-synth-local --no-build-isolation",
              file=sys.stderr)
        sys.exit(1)

    # Ensure both the standard KiCad symbols and ~/KiCad (EasyEDA library) are on
    # the search path. Setting KICAD_SYMBOL_DIR disables circuit-synth's built-in
    # fallback to /Applications/KiCad, so we must include it explicitly.
    _kicad_system = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
    _kicad_user = str(pathlib.Path.home() / "KiCad")
    _existing = os.environ.get("KICAD_SYMBOL_DIR", "")
    _paths = [p for p in [_kicad_user, _kicad_system, _existing] if p]
    os.environ["KICAD_SYMBOL_DIR"] = ":".join(_paths)

    # circuit-synth crashes on incremental update (SheetManager bug) so we must
    # generate fresh.  To avoid forcing a KiCad restart, we generate into a
    # temporary folder and then overwrite the real output folder file-by-file.
    # KiCad detects the in-place modification and shows a one-click "Reload"
    # prompt instead of losing track of the open project.
    STAGING = "speakeasy_staging"
    OUTPUT  = "speakeasy"

    shutil.rmtree(STAGING, ignore_errors=True)

    circuit_obj = speakeasy_board()

    project_result = circuit_obj.generate_kicad_project(
        project_name=STAGING,
        placement_algorithm="hierarchical",
        generate_pcb=True,
        preserve_user_components=False,
    )
    # Stabilise the circuit-synth internal tstamp in Speakeasy.json
    import re as _re
    _json_path = f"{STAGING}/Speakeasy.json"
    try:
        _jtext = open(_json_path).read()
        _jtext = _re.sub(r'"tstamps":\s*"[^"]*"', '"tstamps": "/speakeasy/"', _jtext, count=1)
        open(_json_path, "w").write(_jtext)
    except Exception:
        pass

    # fix_power_symbol_overlaps(f"{STAGING}/Speakeasy.kicad_sch")
    add_lcsc_numbers(f"{STAGING}/Speakeasy.kicad_sch")
    preserve_component_uuids(
        f"{OUTPUT}/Speakeasy.kicad_sch", f"{STAGING}/Speakeasy.kicad_sch",
        net_path=f"{STAGING}/Speakeasy.net",
        pro_path=f"{STAGING}/Speakeasy.kicad_pro",
    )

    # Copy staging → output, preserving any KiCad-managed files (e.g. .kicad_pcb
    # with user-placed components) that are not regenerated by circuit-synth.
    pathlib.Path(OUTPUT).mkdir(exist_ok=True)
    for src in pathlib.Path(STAGING).iterdir():
        dst = pathlib.Path(OUTPUT) / src.name
        shutil.copy2(src, dst)
    shutil.rmtree(STAGING)

    print("KiCad project: speakeasy/speakeasy.kicad_pro")

    bom = circuit_obj.generate_bom(project_name=STAGING)
    if bom["success"]:
        print(f"BOM: {OUTPUT}/{pathlib.Path(bom['file']).name}  ({bom['component_count']} components)")
    else:
        print(f"BOM failed: {bom.get('error')}")

    write_jlcpcb_bom(f"{OUTPUT}/Speakeasy.kicad_sch", f"{OUTPUT}/speakeasy_jlcpcb_bom.csv")

    pdf = circuit_obj.generate_pdf_schematic(project_name=STAGING)
    if pdf["success"]:
        print(f"PDF: {OUTPUT}/{pathlib.Path(pdf['file']).name}")
    else:
        print(f"PDF failed: {pdf.get('error')}")

    gerbers = circuit_obj.generate_gerbers(project_name=STAGING)
    if gerbers["success"]:
        print(f"Gerbers: {gerbers['output_dir']}  ({len(gerbers['gerber_files'])} files)")
    else:
        print(f"Gerbers failed: {gerbers.get('error')}")
