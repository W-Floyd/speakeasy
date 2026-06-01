"""Speakeasy Board — ESP32-S3-MINI-1 + MAX98357A I2S Amplifier

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
- I2S pin assignment matches speakeasy firmware:
    IO4 → MAX98357A DIN     (I2S data out from ESP)
    IO5 → MAX98357A BCLK    (bit clock)
    IO6 → MAX98357A LRCLK   (left/right clock)
- MAX98357A SD_MODE pin 4 pulled high via 100k → left-channel/enable
  (Sendspin sends mono audio on left channel)
- MAX98357A OUTP/OUTN connect directly to the speaker terminal (no DC-blocking cap;
  the MAX98357A is a filterless Class D amp with no DC offset on the outputs)

Output: generates speakeasy/Speakeasy.net (KiCad netlist) and speakeasy_jlcpcb_bom.csv.
Import the netlist into KiCad (Tools → Update Schematic from Netlist) to sync changes.
"""

import csv
import pathlib
from collections import defaultdict

from skidl import Net, Part, subcircuit
from skidl import generate_netlist, generate_xml, generate_schematic, ERC
from skidl import KICAD, set_default_tool, lib_search_paths

# Use KiCad library format and add search paths.
# EasyEDA (~/KiCad/EasyEDA.kicad_sym) must come before system libs so
# EasyEDA-imported parts shadow any same-named KiCad built-ins.
set_default_tool(KICAD)
_kicad_system = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
_kicad_user = str(pathlib.Path.home() / "KiCad")
# Prepend in reverse order so user (EasyEDA) ends up ahead of system libs
for _p in [_kicad_system, _kicad_user]:
    if _p not in lib_search_paths[KICAD]:
        lib_search_paths[KICAD].insert(0, _p)


# JLCPCB LCSC part numbers keyed by designator.
# ⚠  Verify U1, U2, C5, J1, J2, SW1/SW2 on lcsc.com before ordering —
#    passives and AMS1117 are well-known basic parts; modules/ICs can change.
LCSC_PARTS = {
    "U1":  "C22356044",  # ESP32-S3-MINI-1U-N4R2
    "U2":  "C910544",    # MAX98357AETE+T TQFN-16
    "U3":  "C6186",      # AMS1117-3.3 SOT-223  (basic part)
    "J1":  "C64659",     # PH-6P SMD 6-pin 2.0mm
    "J2":  "C20608465",  # 210-A-SMD/02 SMD screw terminal
    # TP1–TP4 are bare test pads — no LCSC part
    "R1":  "C25905",     # 5.1kΩ 0402 1% (basic)
    "R2":  "C25905",
    "R3":  "C25744",     # 10kΩ  0402 1% (basic)
    "R4":  "C25741",     # 100kΩ 0402 1% (basic)
    "C1":  "C15850",     # 10uF 0805 X5R 10V (basic)
    "C2":  "C15850",
    "C3":  "C15850",
    "C4":  "C14663",     # 100nF 0402 X7R 16V (basic)
    "C5":  "C52923",     # 1uF   0402 X5R 16V (basic)
    "C6":  "C14663",     # 100nF 0402 X7R 16V (basic)
    "SW1": "C318884",    # SMD tact switch 6×6mm  ← verify footprint
    "SW2": "C318884",
}


@subcircuit
def speakeasy_board():

    # ── Modules / ICs ──────────────────────────────────────────────────────

    esp32 = Part(
        "EasyEDA", "ESP32-S3-MINI-1U-N4R2",
        footprint="EasyEDA:BULETM-SMD_ESPRESSIF_ESP32-S3-MINI-1U-N8",
        value="ESP32-S3-MINI-1U-N4R2",
    )
    esp32.ref = "U1"

    # MAX98357AETE+T: mono I2S input → Class D amplifier, 2.5–5.5V, up to 3.2W/4Ω
    dac = Part(
        "EasyEDA", "MAX98357AETE+T",
        footprint="EasyEDA:TQFN-16_L3.0-W3.0-P0.50-BL-EP1.5",
        value="MAX98357AETE+T",
    )
    dac.ref = "U2"

    # AMS1117-3.3: 800mA LDO, VBUS (5V) → 3.3V for ESP32 module
    ldo = Part(
        "EasyEDA", "AMS1117-3.3",
        footprint="EasyEDA:SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR",
        value="AMS1117-3.3",
    )
    ldo.ref = "U3"

    # ── Connectors ─────────────────────────────────────────────────────────

    # 6-pin JST PH 2.0mm SMD (mates with panel-mount USB-C cable, female PH)
    # Pinout: 1=GND  2=D+  3=D-  4=CC2  5=CC1  6=VCC  7/8=mounting tabs
    # simp-sexp reads .kicad_sym as latin-1; re-encode the UTF-8 name to match.
    _ph6p = "PH-6P立贴".encode("utf-8").decode("latin-1")
    usbc = Part(
        "EasyEDA", _ph6p,
        footprint="EasyEDA:CONN-SMD_6P-P2.0-L14.0-W5.4",
        value="PH-6P立贴",
    )
    usbc.ref = "J1"

    # 2-pin SMD screw terminal for speaker wires
    spkr_conn = Part(
        "EasyEDA", "210-A-SMD_02",
        footprint="EasyEDA:CONN-SMD_210-A-SMD-02",
        value="210-A-SMD/02",
    )
    spkr_conn.ref = "J2"

    # UART test pads — probe points for 3V3, GND, TXD0, RXD0
    _tp_fp = "TestPoint:TestPoint_Pad_D1.5mm"
    tp_3v3 = Part("Connector", "TestPoint", footprint=_tp_fp, value="3V3")
    tp_3v3.ref = "TP1"
    tp_gnd = Part("Connector", "TestPoint", footprint=_tp_fp, value="GND")
    tp_gnd.ref = "TP2"
    tp_tx = Part("Connector", "TestPoint", footprint=_tp_fp, value="TXD0")
    tp_tx.ref = "TP3"
    tp_rx = Part("Connector", "TestPoint", footprint=_tp_fp, value="RXD0")
    tp_rx.ref = "TP4"

    # ── Passive components ─────────────────────────────────────────────────

    # CC1/CC2 pull-down resistors — 5.1k to GND, identifies board as 5V/900mA sink
    r_cc1 = Part("Device", "R", footprint="Resistor_SMD:R_0402_1005Metric", value="5.1k")
    r_cc1.ref = "R1"
    r_cc2 = Part("Device", "R", footprint="Resistor_SMD:R_0402_1005Metric", value="5.1k")
    r_cc2.ref = "R2"

    # EN pullup — supplements ESP32 module internal pullup for clean power-on reset
    r_en = Part("Device", "R", footprint="Resistor_SMD:R_0402_1005Metric", value="10k")
    r_en.ref = "R3"

    # MAX98357A SD_MODE (pin 4): 100k to 3.3V → left-channel mode enabled
    r_sd = Part("Device", "R", footprint="Resistor_SMD:R_0402_1005Metric", value="100k")
    r_sd.ref = "R4"

    # LDO input bulk cap (+5V rail, near U3 input)
    c_ldo_in = Part("Device", "C", footprint="Capacitor_SMD:C_0805_2012Metric", value="10uF")
    c_ldo_in.ref = "C1"

    # LDO output cap (+3.3V rail — required for AMS1117 stability: min 10uF)
    c_ldo_out = Part("Device", "C", footprint="Capacitor_SMD:C_0805_2012Metric", value="10uF")
    c_ldo_out.ref = "C2"

    # ESP32 +3.3V bulk decoupling
    c_esp_bulk = Part("Device", "C", footprint="Capacitor_SMD:C_0805_2012Metric", value="10uF")
    c_esp_bulk.ref = "C3"

    # ESP32 +3.3V high-frequency bypass
    c_esp_bypass = Part("Device", "C", footprint="Capacitor_SMD:C_0402_1005Metric", value="100nF")
    c_esp_bypass.ref = "C4"

    # MAX98357A VDD bulk decoupling (+5V rail, near U2)
    c_dac_bulk = Part("Device", "C", footprint="Capacitor_SMD:C_0402_1005Metric", value="1uF")
    c_dac_bulk.ref = "C5"

    # MAX98357A VDD high-frequency bypass (as close to chip as possible)
    c_dac_bypass = Part("Device", "C", footprint="Capacitor_SMD:C_0402_1005Metric", value="100nF")
    c_dac_bypass.ref = "C6"

    # Boot button: pulls IO0 low to enter USB download mode
    boot_btn = Part("Switch", "SW_Push", footprint="Button_Switch_SMD:SW_SPST_CK_RS282G05A3", value="BOOT")
    boot_btn.ref = "SW1"

    # Reset button: pulls EN low to reset the ESP32
    rst_btn = Part("Switch", "SW_Push", footprint="Button_Switch_SMD:SW_SPST_CK_RS282G05A3", value="RST")
    rst_btn.ref = "SW2"

    # ── Nets ───────────────────────────────────────────────────────────────

    vbus    = Net("+5V")     # 5V from panel-mount USB-C
    vcc_3v3 = Net("+3.3V")  # 3.3V regulated (ESP32 supply)
    gnd     = Net("GND")

    usb_dp  = Net("USB_DP")  # USB D+  → ESP32 USB_D+
    usb_dm  = Net("USB_DM")  # USB D-  → ESP32 USB_D-

    cc1 = Net("CC1")
    cc2 = Net("CC2")

    i2s_bclk  = Net("I2S_BCLK")   # IO5
    i2s_lrclk = Net("I2S_LRCLK")  # IO6
    i2s_dout  = Net("I2S_DOUT")   # IO4

    en_net  = Net("EN")
    gpio0   = Net("GPIO0")
    sd_mode = Net("SD_MODE")
    uart_tx = Net("UART_TX")  # ESP TXD0 → dongle RX
    uart_rx = Net("UART_RX")  # ESP RXD0 ← dongle TX

    spkr_p = Net("SPKR_P")
    spkr_n = Net("SPKR_N")

    # ── JST-XH 6-pin (panel-mount USB-C interface) ─────────────────────────
    # Pin 1=GND  2=D+  3=D-  4=CC2  5=CC1  6=VCC  7/8=mounting tabs

    usbc[1] += gnd
    usbc[2] += usb_dp
    usbc[3] += usb_dm
    usbc[4] += cc2
    usbc[5] += cc1
    usbc[6] += vbus
    usbc[7] += gnd
    usbc[8] += gnd

    # CC pull-downs on PCB side: identifies board as USB power sink
    r_cc1[1] += cc1
    r_cc1[2] += gnd
    r_cc2[1] += cc2
    r_cc2[2] += gnd

    # ── LDO: VBUS → 3.3V ──────────────────────────────────────────────────

    ldo["VIN"]  += vbus
    ldo["VOUT"] += vcc_3v3
    ldo["GND"]  += gnd

    c_ldo_in[1]  += vbus
    c_ldo_in[2]  += gnd
    c_ldo_out[1] += vcc_3v3
    c_ldo_out[2] += gnd

    # ── ESP32-S3-WROOM-1 ──────────────────────────────────────────────────

    # SKiDL connects all pins named "3V3" / "GND" automatically when multiple exist
    esp32["3V3"] += vcc_3v3
    esp32["GND"] += gnd
    esp32["EN"]  += en_net

    # Native USB peripheral (no CH340/CP2102 needed)
    # ESP32-S3 MINI: IO20 = USB D+, IO19 = USB D-
    esp32["IO20"] += usb_dp
    esp32["IO19"] += usb_dm

    # I2S → MAX98357A (must match speakeasy.yaml GPIO assignments)
    esp32["IO4"] += i2s_dout
    esp32["IO5"] += i2s_bclk
    esp32["IO6"] += i2s_lrclk

    # Boot/reset pins
    esp32["IO0"]  += gpio0
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

    # SD_MODE high via 100k to 3.3V (left channel, 9dB gain)
    r_sd[1] += vcc_3v3
    r_sd[2] += sd_mode

    # VDD decoupling (Class D switching; place these as close as possible)
    c_dac_bulk[1]   += vbus
    c_dac_bulk[2]   += gnd
    c_dac_bypass[1] += vbus
    c_dac_bypass[2] += gnd

    # ── Speaker connector ───────────────────────────────────────────────────

    spkr_conn[1] += spkr_p
    spkr_conn[2] += spkr_n

    # ── UART test pads ─────────────────────────────────────────────────────

    tp_3v3[1] += vcc_3v3
    tp_gnd[1] += gnd
    tp_tx[1]  += uart_tx
    tp_rx[1]  += uart_rx


def write_jlcpcb_bom(out_path):
    """Write a JLCPCB-compatible BOM CSV from the current SKiDL circuit."""
    import builtins
    default_circuit = builtins.default_circuit

    groups = defaultdict(list)
    for part in sorted(default_circuit.parts, key=lambda p: p.ref):
        ref = part.ref
        if not ref or ref.startswith("#"):
            continue
        value = str(part.value) if part.value else ""
        fp = str(part.footprint) if part.footprint else ""
        lcsc = LCSC_PARTS.get(ref, "")
        groups[(value, fp, lcsc)].append(ref)

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for (value, fp, lcsc), refs in sorted(groups.items()):
            w.writerow([value, ",".join(sorted(refs)), fp, lcsc])

    print(f"JLCPCB BOM: {out_path}")


def generate_reference_schematic():
    """Generate a reference schematic in a subprocess to avoid SKiDL state pollution.

    generate_schematic() modifies internal SKiDL circuit state in ways that break
    generate_netlist() and part attribute access when called in the same process.
    Running it in a subprocess keeps the main circuit pristine.

    Returns the path to the .kicad_sch file with the most symbol instances,
    or None on failure.
    """
    import subprocess
    import sys
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="speakeasy_sch_")
    _kicad_system = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
    _kicad_user = str(pathlib.Path.home() / "KiCad")

    script = f"""
import sys, pathlib
sys.path.insert(0, {str(pathlib.Path(__file__).parent)!r})
from skidl import *
from skidl import KICAD, set_default_tool, lib_search_paths, generate_schematic
set_default_tool(KICAD)
lib_search_paths[KICAD].insert(0, {_kicad_system!r})
lib_search_paths[KICAD].insert(0, {_kicad_user!r})
from speakeasy_board import speakeasy_board
speakeasy_board()
generate_schematic(filepath={tmp_dir!r}, top_name='ref', auto_stub=True)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True,
    )
    # generate_schematic warns but exits 0 on routing fallback — that's fine
    if result.returncode != 0:
        print(f"Warning: reference schematic generation failed (exit {result.returncode}); "
              "missing components will need manual placement")
        print("  stderr:", result.stderr[-300:] if result.stderr else "(none)")
        return None

    # Pick the largest .kicad_sch — SKiDL generates a hierarchical schematic where
    # the sub-sheet (containing actual component instances) is much bigger than the
    # top-level sheet (which only has lib_symbols and a sheet link).
    files = list(pathlib.Path(tmp_dir).rglob("*.kicad_sch"))
    if not files:
        return None
    return str(max(files, key=lambda f: f.stat().st_size))


def sync_schematic_from_circuit(sch_path, ref_sch_path=None):
    """Sync an existing .kicad_sch with the current SKiDL circuit using kicad-skip.

    For each real component (non-power) in the schematic:
      - If the ref exists in the SKiDL circuit: update Value, Footprint, LCSC.
      - If the ref was deleted from the circuit: warn (manual removal needed).

    For each SKiDL part missing from the schematic:
      - Auto-place it by copying its symbol instance and lib definition from
        ref_sch_path (a pre-generated reference schematic from generate_reference_schematic()).

    Wire/net topology is NOT touched — only component placement and properties.
    """
    import builtins
    import copy
    import skip

    default_circuit = builtins.default_circuit

    # Build a dict of {ref: part} from the live SKiDL circuit, ignoring power symbols
    skidl_parts = {
        p.ref: p
        for p in default_circuit.parts
        if p.ref and not p.ref.startswith("#")
    }

    sch = skip.Schematic(sch_path)

    # Build a dict of {ref: symbol} for all real schematic symbols
    sch_syms = {}
    for sym in sch.symbol:
        try:
            ref = sym.property.Reference.value
        except Exception:
            continue
        if ref and not ref.startswith("#"):
            sch_syms[ref] = sym

    updated = []
    not_in_circuit = []
    missing_refs = [ref for ref in skidl_parts if ref not in sch_syms]

    # ── Update properties on existing symbols ─────────────────────────────

    for ref, sym in sch_syms.items():
        part = skidl_parts.get(ref)
        if part is None:
            not_in_circuit.append(ref)
            continue

        changed = False

        new_val = str(part.value) if part.value else ""
        if sym.property.Value.value != new_val:
            sym.property.Value.value = new_val
            changed = True

        new_fp = str(part.footprint) if part.footprint else ""
        if sym.property.Footprint.value != new_fp:
            sym.property.Footprint.value = new_fp
            changed = True

        new_lcsc = LCSC_PARTS.get(ref, "")
        try:
            cur_lcsc = sym.property.LCSC.value
        except Exception:
            cur_lcsc = None

        if new_lcsc and cur_lcsc != new_lcsc:
            if cur_lcsc is None:
                lcsc_prop = sym.property.Value.clone()
                lcsc_prop.name = "LCSC"
                lcsc_prop.value = new_lcsc
            else:
                sym.property.LCSC.value = new_lcsc
            changed = True

        if changed:
            updated.append(ref)

    # ── Auto-place missing symbols from a reference schematic ──────────────

    placed = []
    still_missing = []

    if missing_refs:
        if ref_sch_path:
            ref_sch = skip.Schematic(ref_sch_path)

            # Index ref symbols and lib_symbols from the reference schematic
            ref_syms = {}
            for sym in ref_sch.symbol:
                try:
                    ref_syms[sym.property.Reference.value] = sym
                except Exception:
                    pass

            # Find lib_symbols block in both trees
            ref_lib_block = next(
                (item for item in ref_sch.tree
                 if isinstance(item, list) and str(item[0]) == "lib_symbols"), None
            )
            tgt_lib_block = next(
                (item for item in sch.tree
                 if isinstance(item, list) and str(item[0]) == "lib_symbols"), None
            )
            if tgt_lib_block is None:
                from sexp import Symbol as SexpSymbol
                tgt_lib_block = [SexpSymbol("lib_symbols")]
                sch.tree.append(tgt_lib_block)

            # Collect lib_ids already in target
            tgt_lib_ids = {
                entry[1] for entry in tgt_lib_block[1:]
                if isinstance(entry, list) and len(entry) > 1
            }

            for ref in missing_refs:
                src_sym = ref_syms.get(ref)
                if src_sym is None:
                    still_missing.append(ref)
                    continue

                # Inject symbol instance
                sch.tree.append(copy.deepcopy(src_sym.raw))

                # Inject lib definition if not already present
                lib_id = src_sym.lib_id.value if hasattr(src_sym, "lib_id") else None
                if lib_id and ref_lib_block and lib_id not in tgt_lib_ids:
                    lib_def = next(
                        (entry for entry in ref_lib_block[1:]
                         if isinstance(entry, list) and len(entry) > 1
                         and entry[1] == lib_id),
                        None,
                    )
                    if lib_def:
                        tgt_lib_block.append(copy.deepcopy(lib_def))
                        tgt_lib_ids.add(lib_id)

                placed.append(ref)
        else:
            still_missing = missing_refs

    sch.write(sch_path)

    if updated:
        print(f"Schematic: updated {len(updated)} component(s): {', '.join(sorted(updated))}")
    if placed:
        print(f"Schematic: placed {len(placed)} new component(s): {', '.join(sorted(placed))}")
    if not updated and not placed:
        print("Schematic: all components up to date")
    if still_missing:
        print(f"Schematic: ⚠ could not auto-place {len(still_missing)} component(s) "
              f"(place manually): {', '.join(sorted(still_missing))}")
    if not_in_circuit:
        print(f"Schematic: ⚠ {len(not_in_circuit)} component(s) removed from circuit, "
              f"delete manually if desired: {', '.join(sorted(not_in_circuit))}")


if __name__ == "__main__":
    OUTPUT = pathlib.Path("speakeasy")
    OUTPUT.mkdir(exist_ok=True)

    speakeasy_board()

    ERC()

    net_path = str(OUTPUT / "Speakeasy.net")
    generate_netlist(file_=net_path)
    print(f"Netlist: {net_path}")

    xml_path = str(OUTPUT / "Speakeasy.xml")
    generate_xml(file_=xml_path)
    print(f"XML BOM:  {xml_path}")

    write_jlcpcb_bom(str(OUTPUT / "speakeasy_jlcpcb_bom.csv"))

    sch_path = str(OUTPUT / "Speakeasy.kicad_sch")
    ref_sch_path = generate_reference_schematic()
    sync_schematic_from_circuit(sch_path, ref_sch_path=ref_sch_path)
