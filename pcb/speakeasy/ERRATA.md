# Speakeasy PCB Errata

## Rev 1

### E1 — J1 connector inverted

**Symptom:** Plugging into USB immediately trips dock overcurrent protection.  
**Root cause:** J1 (6-pin JST PH 2.0mm panel-mount USB-C header, C64659) is populated inverted, reversing VBUS and GND (and swapping all signal pins).  
**Workaround:** Rework — reflow and flip J1 180°.  
**Fix for rev 2:** Verify connector orientation in footprint vs. mating cable before fab. Add a pin-1 marker to the silkscreen adjacent to J1.
