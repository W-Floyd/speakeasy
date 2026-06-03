"""Utility functions for speakeasy_board.py.

Covers: LCSC component creation, multi-pin connection, KiCad post-processing
(UUID stabilisation, LCSC property stamping, power-symbol overlap fixes),
and JLCPCB BOM export.
"""

from lookup_part import lookup
from circuit_synth import Component

# Populated by component_from_lcsc() as components are instantiated.
# Used by add_lcsc_numbers() and write_jlcpcb_bom() to stamp LCSC properties.
LCSC_REGISTRY: dict = {}


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
    LCSC_REGISTRY[ref] = lcsc
    return Component(ref=ref, **overrides)


def connect(component, pin_name, net):
    """Connect all pins named pin_name to net.

    circuit-synth's component[name] only wires the first matching pin.
    This helper finds every pin with the given name (e.g. duplicate VOUT
    or GND pads) and connects them all, so nothing is silently left floating.
    """
    from circuit_synth.kicad.kicad_symbol_cache import SymbolLibCache

    sym_data = SymbolLibCache.get_symbol_data(component.symbol)
    pins = sym_data.get("pins", {})

    if isinstance(pins, dict):
        items = [(num, info.get("name", "")) for num, info in pins.items()]
    else:
        items = [(p.get("number"), p.get("name", "")) for p in (pins or [])]

    matched = [num for num, name in items if name == pin_name]

    if not matched:
        component[pin_name] += net
        return

    for num in matched:
        try:
            component[int(num)] += net
        except (ValueError, TypeError, Exception):
            component[num] += net


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

    caps = [c for c in sch.components if c.lib_id == "Device:C"]
    unconnected_bottoms = []
    for cap in caps:
        cx = round(cap.position.x, 2)
        cy = round(cap.position.y, 2)
        bottom = (cx, round(cy + PIN_OFFSET, 2))
        if bottom not in gnd_xy:
            unconnected_bottoms.append(bottom)

    misplaced = [c for c in pwr
                 if c.lib_id == "power:GND"
                 and (round(c.position.x, 2), round(c.position.y, 2)) in vbus_xy]

    fixed = 0
    for gnd_sym in misplaced:
        if not unconnected_bottoms:
            break
        gx = round(gnd_sym.position.x, 2)
        target = next((b for b in unconnected_bottoms if b[0] == gx), None)
        if target is None:
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
        lcsc = LCSC_REGISTRY.get(comp.reference)
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
            block = re.sub(r'(\(uuid\s+)"[^"]+"', rf'\1"{old_entry[1]}"', block, count=1)
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
            """Return {ref: tstamp} from a KiCad net file."""
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
                new_net = re.sub(r'\(date "[^"]*"\)', '(date "1970-01-01T00:00:00+0000")', new_net)
                open(net_path, "w").write(new_net)
                old_net_tstamps = extract_net_tstamps(old_net)
                new_net_tstamps = extract_net_tstamps(new_net)

                result_net = new_net
                for ref, new_ts in new_net_tstamps.items():
                    old_ts = old_net_tstamps.get(ref)
                    if old_ts and old_ts != new_ts:
                        result_net = result_net.replace(
                            f'(tstamps "{new_ts}")', f'(tstamps "{old_ts}")', 1
                        )

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

    # Ref prefixes that are never assembled (test points, holes, fiducials)
    _SKIP_PREFIXES = ("TP", "H", "FID", "MH", "MP")
    # Footprint keywords that indicate non-assembled parts
    _SKIP_FP_KEYWORDS = ("TestPoint", "MountingHole", "Fiducial")

    sch = ksa.load_schematic(sch_path)
    rows = []
    for comp in sch.components:
        ref = comp.reference
        if not ref or ref.startswith("#"):
            continue
        if any(ref.startswith(p) for p in _SKIP_PREFIXES):
            continue
        fp = comp.footprint or ""
        if any(kw in fp for kw in _SKIP_FP_KEYWORDS):
            continue
        # Skip DNP components if the attribute is exposed
        if getattr(comp, "dnp", False):
            continue
        lcsc = LCSC_REGISTRY.get(ref, "")
        value = comp.value or ""
        rows.append((ref, value, fp, lcsc))

    # Group by LCSC number when available (same part regardless of schematic value),
    # otherwise fall back to (value, footprint) to avoid merging unrelated parts.
    by_lcsc:    dict = defaultdict(list)  # lcsc → [(ref, value, fp)]
    by_valuefp: dict = defaultdict(list)  # (value, fp) → [(ref, value, fp)]
    for ref, value, fp, lcsc in rows:
        if lcsc:
            by_lcsc[lcsc].append((ref, value, fp))
        else:
            by_valuefp[(value, fp)].append((ref, value, fp))

    output_rows = []
    for lcsc, entries in by_lcsc.items():
        refs  = sorted(e[0] for e in entries)
        value = entries[0][1]
        fp    = entries[0][2]
        output_rows.append((value, ",".join(refs), fp, lcsc))
    for (value, fp), entries in by_valuefp.items():
        refs = sorted(e[0] for e in entries)
        output_rows.append((value, ",".join(refs), fp, ""))
    output_rows.sort(key=lambda r: r[1])

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for row in output_rows:
            w.writerow(row)

    print(f"JLCPCB BOM: {out_path}")
