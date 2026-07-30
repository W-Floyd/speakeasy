#!/usr/bin/env bash
# Builds each firmware variant's Docker stage, extracts the OTA bin, and
# prints a size comparison table with feature-delta annotations.
#
# Variants are read from variants.yaml so this stays in sync with the
# generated Dockerfile — do not hardcode stage names here.
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

# ── Helpers ───────────────────────────────────────────────────────────────────

hr() { printf '%0.s─' {1..60}; echo; }

extract_from_stage() {
    local stage="$1" src="$2" dst="$3"
    local tag="speakeasy-size-${stage}"
    docker build --quiet --target "${stage}" -t "${tag}" "${REPO_ROOT}" >/dev/null
    local cid
    cid=$(docker create "${tag}")
    docker cp "${cid}:${src}" "${dst}" 2>/dev/null
    docker rm "${cid}" >/dev/null
}

fmt_kb() { printf '%d KiB' $(( $1 / 1024 )); }

delta_str() {
    local d=$1
    if (( d > 0 )); then printf '+%d KiB' $(( d / 1024 ))
    else printf '%d KiB' $(( d / 1024 ))
    fi
}

# Size stored in SIZE_<key> where key = stage name with - replaced by _
set_size() { local v="${2// /}"; eval "SIZE_${1//-/_}=${v}"; }
get_size() { eval "echo \${SIZE_${1//-/_}}"; }
has_size() { eval "[[ -n \${SIZE_${1//-/_}:-} ]]"; }

# Read a top-level YAML list (`key:` followed by `  - item` lines).
read_list() {
    awk -v key="$1" '
        $0 ~ "^" key ":[[:space:]]*$" { inlist = 1; next }
        inlist && /^[[:space:]]+-[[:space:]]*/ {
            sub(/^[[:space:]]*-[[:space:]]*/, "")
            sub(/[[:space:]]*#.*$/, "")
            if ($0 != "") print
            next
        }
        inlist && /^[^[:space:]#]/ { inlist = 0 }
    ' "${REPO_ROOT}/variants.yaml"
}

contains() {
    local needle="$1"; shift
    local x
    for x in "$@"; do [[ "${x}" == "${needle}" ]] && return 0; done
    return 1
}

# ── Variant definitions (from variants.yaml) ──────────────────────────────────

ESPHOME_VARIANTS=()
while IFS= read -r v; do [[ -n "${v}" ]] && ESPHOME_VARIANTS+=("${v}"); done < <(read_list ci)

SNAPCLIENT_VARIANTS=()
while IFS= read -r v; do [[ -n "${v}" ]] && SNAPCLIENT_VARIANTS+=("${v}"); done < <(read_list snapclient-ci)

if (( ${#ESPHOME_VARIANTS[@]} == 0 && ${#SNAPCLIENT_VARIANTS[@]} == 0 )); then
    echo "ERROR: no variants parsed from ${REPO_ROOT}/variants.yaml" >&2
    exit 1
fi

# Turn a variant name into a human label: ots-sc-bt → OTS Snapcast + BT
pretty() {
    local out="" part
    local IFS='-'
    for part in $1; do
        case "${part}" in
            ots)    part="OTS" ;;
            pcb)    part="PCB" ;;
            ss)     part="Sendspin" ;;
            sc)     part="Snapcast" ;;
            bt)     part="+ BT" ;;
            nopull) part="(no pull OTA)" ;;
            2ch)    part="2ch" ;;
        esac
        out="${out:+${out} }${part}"
    done
    printf '%s' "${out}"
}

# stage / src-path-in-image / label
# ESPHome src is a directory; snapclient src is a file.
STAGES=()
SRCS=()
LABELS=()

for v in "${SNAPCLIENT_VARIANTS[@]}"; do
    STAGES+=("snapclient-${v}")
    SRCS+=("/output/snapclient-${v}/snapclient-${v}-ota.bin")
    if [[ "${v}" == *-nopull ]]; then
        LABELS+=("snapclient $(pretty "${v}")")
    else
        LABELS+=("snapclient $(pretty "${v}") (pull OTA)")
    fi
done

for v in "${ESPHOME_VARIANTS[@]}"; do
    STAGES+=("esphome-${v}")
    SRCS+=("/output/speakeasy-${v}")
    LABELS+=("ESPHome $(pretty "${v}")")
done

# ── Extract all variants ──────────────────────────────────────────────────────

TMPDIR_BINS=$(mktemp -d)
trap 'rm -rf "${TMPDIR_BINS}"' EXIT

echo "Building and extracting firmware stages..."
hr

for i in "${!STAGES[@]}"; do
    stage="${STAGES[$i]}"
    src="${SRCS[$i]}"
    label="${LABELS[$i]}"
    dst="${TMPDIR_BINS}/${stage}"

    printf "  %-45s " "${label}..."

    if [[ "${src}" != *.bin ]]; then
        # ESPHome: extract whole output dir, find OTA bin inside
        extract_from_stage "${stage}" "${src}" "${dst}"
        ota_bin=$(find "${dst}" -name '*ota*.bin' | head -1)
        if [[ -z "${ota_bin}" ]]; then
            # Fall back to largest .bin (not merged/bootloader)
            ota_bin=$(find "${dst}" -name '*.bin' ! -name 'merged*' -print0 \
                      | xargs -0 wc -c 2>/dev/null \
                      | sort -n | tail -2 | head -1 | awk '{print $2}')
        fi
        set_size "${stage}" "$(wc -c < "${ota_bin}")"
    else
        extract_from_stage "${stage}" "${src}" "${dst}.bin"
        set_size "${stage}" "$(wc -c < "${dst}.bin")"
    fi

    printf '%s\n' "$(fmt_kb "$(get_size "${stage}")")"
done

# ── Size table ────────────────────────────────────────────────────────────────

echo ""
hr
printf '%-45s  %10s\n' "Variant" "OTA size"
hr
for i in "${!STAGES[@]}"; do
    printf '%-45s  %10s\n' "${LABELS[$i]}" "$(fmt_kb "$(get_size "${STAGES[$i]}")")"
done
hr

# ── Feature deltas ────────────────────────────────────────────────────────────

echo ""
echo "Feature cost:"
hr

delta() {
    local base="$1" feature="$2" label="$3"
    has_size "${base}" && has_size "${feature}" || return 0
    printf '  %-38s  %s\n' "${label}" \
        "$(delta_str $(( $(get_size "${feature}") - $(get_size "${base}") )))"
}

# Pull OTA cost: any snapclient variant that also has a -nopull counterpart.
for v in "${SNAPCLIENT_VARIANTS[@]}"; do
    [[ "${v}" == *-nopull ]] && continue
    contains "${v}-nopull" "${SNAPCLIENT_VARIANTS[@]}" || continue
    delta "snapclient-${v}-nopull" "snapclient-${v}" "Pull OTA (snapclient $(pretty "${v}"))"
done

# Bluetooth cost: any ESPHome variant that also has a -bt counterpart.
for v in "${ESPHOME_VARIANTS[@]}"; do
    [[ "${v}" == *-bt ]] && continue
    contains "${v}-bt" "${ESPHOME_VARIANTS[@]}" || continue
    delta "esphome-${v}" "esphome-${v}-bt" "Bluetooth ($(pretty "${v}"))"
done

# Sanity check: within a hardware target, the BT cost should be similar for the
# Sendspin and Snapcast variants. A large divergence hints at unrelated config drift.
bt_delta() {
    has_size "esphome-$1" && has_size "esphome-$1-bt" || return 1
    echo $(( $(get_size "esphome-$1-bt") - $(get_size "esphome-$1") ))
}

for hw in $(printf '%s\n' "${ESPHOME_VARIANTS[@]}" | cut -d- -f1 | sort -u); do
    d1=$(bt_delta "${hw}-ss") || continue
    d2=$(bt_delta "${hw}-sc") || continue
    diff=$(( d1 - d2 ))
    (( diff < 0 )) && diff=$(( -diff ))
    if (( diff > 4096 )); then
        echo ""
        echo "  NOTE: BT deltas differ by $(fmt_kb ${diff}) between $(pretty "${hw}") ss and sc variants"
        echo "  (may indicate unrelated config differences)"
    fi
done

hr
