#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") [-v variant] [-p] <device> [device...]
       $(basename "$0") [-v variant] --usb [--port <port>] [--ssid <ssid> --password <password>] [--log]

Flash a snapclient binary extracted from the Docker image.

OTA mode (default):
  Flash OTA binary over HTTP to one or more network devices.

USB mode (--usb):
  Flash the full merged binary via esptool to a USB-connected device, then
  optionally provision WiFi credentials via the serial improv protocol.

Options:
  -v variant          sdkconfig variant to flash (default: ots)
                        ots  — ESP32-S3 Supermini / Speakeasy Lowcost PCB
                               (LRCLK/BCLK/DOUT on GPIO 4/5/6)
                        pcb  — custom Speakeasy PCB
                               (DOUT/BCLK/LRCLK on GPIO 4/5/6)
                        append -nopull to disable automatic OTA pull from GitHub Pages
  -p, --parallel      flash all devices concurrently — OTA mode only
  --usb               USB flash mode using esptool
  --port <port>       serial port for USB flash / improv (auto-detected if omitted)
  --ssid <ssid>       WiFi SSID for serial improv provisioning
  --password <pass>   WiFi password for serial improv provisioning
  --log               stream serial output after flash/provision (Ctrl+C to exit)
  -h, --help          show this help

OTA steps:
  1. Build the Docker stage for the variant (uses cache if already built)
  2. Extract the OTA binary from the image
  3. Parse the firmware binary and display version/SHA256 details
  4. For each device:
     a. Read the running firmware for comparison
     b. Skip if already running the same firmware (SHA256 match)
     c. Upload via HTTP POST /api/ota/upload
     d. Poll /api/ota/status until the device reboots and SHA256 is confirmed

USB steps:
  1. Build the Docker stage for the variant (uses cache if already built)
  2. Extract merged.bin from the image
  3. Auto-detect ESP32-S3 USB port (VID 0x303A) or use --port
  4. Flash via esptool.py (chip: esp32s3, baud: 921600)
  5. If --ssid is given: provision WiFi via serial improv protocol
  6. If --log is given: stream serial output until Ctrl+C
EOF
    exit 1
}

# ── Arg parsing ───────────────────────────────────────────────────────────────

VARIANT="ots"
PARALLEL=0
USB=0
PORT=""
SSID=""
PASSWORD=""
LOG=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v) VARIANT="${2:?-v requires a variant argument}"; shift 2 ;;
        -p|--parallel) PARALLEL=1; shift ;;
        --usb) USB=1; shift ;;
        --port) PORT="${2:?--port requires an argument}"; shift 2 ;;
        --ssid) SSID="${2:?--ssid requires an argument}"; shift 2 ;;
        --password) PASSWORD="${2:?--password requires an argument}"; shift 2 ;;
        --log) LOG=1; shift ;;
        -h|--help) usage ;;
        *) break ;;
    esac
done

STAGE="snapclient-${VARIANT}"
OTA_BIN="${STAGE}-ota.bin"
IMAGE_TAG="speakeasy-${STAGE}-extract"
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

if [[ "${USB}" -eq 1 ]]; then
    [[ -n "${SSID}" && -z "${PASSWORD}" ]] && { echo "ERROR: --ssid requires --password" >&2; usage; }
    [[ -z "${SSID}" && -n "${PASSWORD}" ]] && { echo "ERROR: --password requires --ssid" >&2; usage; }
else
    [[ $# -lt 1 ]] && usage
    DEVICES=("$@")
fi

# ── Helpers ───────────────────────────────────────────────────────────────────

parse_app_desc() {
    esptool image-info "$1" 2>/dev/null
}

dev_status_json() {
    curl -sf --max-time 3 "http://$1:8000/api/ota/status" 2>/dev/null || true
}

json_field() {
    echo "$1" | jq -r --arg k "$2" '.[$k] // empty'
}

# Detect the first ESP32-S3 USB serial port by Espressif VID (0x303A).
detect_port() {
    python3 - <<'PYEOF'
import sys
try:
    import serial.tools.list_ports
except ImportError:
    sys.exit("ERROR: pyserial not installed — run: pip install pyserial")
ports = [p for p in serial.tools.list_ports.comports() if p.vid == 0x303A]
if not ports:
    sys.exit("ERROR: no ESP32 device found (VID 0x303A) — connect via USB or use --port")
if len(ports) > 1:
    names = ', '.join(p.device for p in ports)
    print(f"WARNING: multiple ESP32 devices found ({names}), using first", file=sys.stderr)
print(ports[0].device)
PYEOF
}

# ── Build + extract ───────────────────────────────────────────────────────────

echo "==> Building stage ${STAGE} (uses cache if already built)..."
docker build \
    -f "${REPO_ROOT}/Dockerfile.snapclient" \
    --target "${STAGE}" \
    -t "${IMAGE_TAG}" \
    "${REPO_ROOT}"

TMP=$(mktemp)
TMP_MERGED=""
trap 'rm -f "${TMP}" "${TMP_MERGED}"' EXIT

CONTAINER=$(docker create "${IMAGE_TAG}")

echo "==> Extracting ${OTA_BIN}..."
docker cp "${CONTAINER}:/output/${STAGE}/${OTA_BIN}" "${TMP}"

if [[ "${USB}" -eq 1 ]]; then
    echo "==> Extracting merged.bin..."
    TMP_MERGED=$(mktemp)
    docker cp "${CONTAINER}:/output/${STAGE}/merged.bin" "${TMP_MERGED}"
fi

docker rm "${CONTAINER}" > /dev/null

echo "==> Parsing firmware binary..."
APP_DESC=$(parse_app_desc "${TMP}")
BIN_SHA=$(echo "${APP_DESC}"  | awk '/^ELF file SHA256:/{print $4}')
BIN_VER=$(echo "${APP_DESC}"  | awk '/^App version:/{print $3}')
BIN_NAME=$(echo "${APP_DESC}" | awk '/^Project name:/{print $3}')
BIN_DATE=$(echo "${APP_DESC}" | awk '/^Compile time:/{$1=$2=""; sub(/^  */,""); print}')
BIN_IDF=$(echo "${APP_DESC}"  | awk '/^ESP-IDF:/{print $2}')

echo ""
echo "  Binary to flash:"
echo "    project : ${BIN_NAME}"
echo "    version : ${BIN_VER}"
echo "    built   : ${BIN_DATE}"
echo "    IDF     : ${BIN_IDF}"
echo "    sha256  : ${BIN_SHA}"

# ── USB flash ─────────────────────────────────────────────────────────────────

if [[ "${USB}" -eq 1 ]]; then
    if [[ -z "${PORT}" ]]; then
        echo "==> Auto-detecting ESP32-S3 USB port..."
        PORT=$(detect_port)
        echo "    found: ${PORT}"
    fi

    echo ""
    echo "══ ${PORT} ════════════════════════════════════════════"
    echo "==> Flashing merged binary via esptool..."
    esptool.py --chip esp32s3 --port "${PORT}" --baud 921600 \
        write_flash 0x0 "${TMP_MERGED}"

    if [[ -n "${SSID}" ]]; then
        if ! command -v improv-setup &>/dev/null; then
            echo "ERROR: improv-setup not found — install with:" >&2
            echo "  cargo install --git https://git.clerie.de/clerie/improv-setup" >&2
            exit 1
        fi
        echo ""
        echo "==> Waiting for device to boot..."
        sleep 5
        echo "==> Provisioning WiFi via serial improv (SSID: ${SSID})..."
        improv-setup device "${PORT}" connect "${SSID}" "${PASSWORD}"
    else
        echo "==> Flash complete. No --ssid given; skipping WiFi provisioning."
        echo "    Connect via serial improv to provision WiFi (baud: 115200)."
    fi

    if [[ "${LOG}" -eq 1 ]]; then
        echo ""
        echo "==> Streaming serial log from ${PORT} (Ctrl+C to exit)..."
        python3 -m serial.tools.miniterm --quiet "${PORT}" 115200
    fi

    echo ""
    echo "==> Done."
    exit 0
fi

# ── OTA: flash one device; returns 0 on success, 1 on failure ─────────────────

flash_device() {
    local device="$1"
    echo ""
    echo "══ ${device} ════════════════════════════════════════════"

    echo "==> Reading current firmware..."
    local dev_json has_status=0 dev_sha=""
    dev_json=$(dev_status_json "${device}")
    if [[ -n "${dev_json}" ]]; then
        has_status=1
        dev_sha=$(json_field "${dev_json}" sha256)
        echo "    project : $(json_field "${dev_json}" project_name)"
        echo "    version : $(json_field "${dev_json}" version)"
        echo "    built   : $(json_field "${dev_json}" compile_date) $(json_field "${dev_json}" compile_time)"
        echo "    IDF     : $(json_field "${dev_json}" idf_version)"
        echo "    sha256  : ${dev_sha}"
        if [[ "${dev_sha}" == "${BIN_SHA}" ]]; then
            echo "==> Already running this firmware (SHA256 match). Skipping."
            return 0
        fi
    else
        echo "    (device unreachable or status endpoint not available — skipping pre-check)"
    fi

    echo "==> Uploading to http://${device}:8000/api/ota/upload..."
    local upload_rc=0
    curl -fS \
        -X POST \
        "http://${device}:8000/api/ota/upload" \
        -H "Content-Type: application/octet-stream" \
        -H "Expect:" \
        --no-buffer \
        --data-binary @"${TMP}" || upload_rc=$?
    # exit 52 = empty reply: device rebooted before sending HTTP response — expected
    if [[ ${upload_rc} -ne 0 && ${upload_rc} -ne 52 ]]; then
        echo "==> ERROR: OTA upload failed for ${device} (curl exit ${upload_rc})" >&2
        return 1
    fi

    echo ""
    echo "==> Upload complete. Waiting for device to reboot..."

    local timeout=30 elapsed=0 new_json new_sha
    while [[ ${elapsed} -lt ${timeout} ]]; do
        sleep 2; elapsed=$((elapsed + 2))
        printf "    polling... %ds\r" "${elapsed}"
        new_json=$(dev_status_json "${device}")
        [[ -z "${new_json}" ]] && continue
        new_sha=$(json_field "${new_json}" sha256)
        if [[ "${new_sha}" == "${BIN_SHA}" ]]; then
            echo "==> Device is back. SHA256 confirmed: ${new_sha}"
            return 0
        elif [[ -n "${new_sha}" && "${new_sha}" != "${dev_sha}" ]]; then
            echo "==> ERROR: device is back but SHA256 does not match the uploaded binary!" >&2
            echo "    expected : ${BIN_SHA}" >&2
            echo "    got      : ${new_sha}" >&2
            return 1
        fi
    done

    echo "==> ERROR: timed out waiting for reboot confirmation." >&2
    return 1
}

# ── OTA: flash each device ────────────────────────────────────────────────────

FAILED=()

if [[ "${PARALLEL}" -eq 1 ]]; then
    PIDS=()
    OUT_FILES=()
    for device in "${DEVICES[@]}"; do
        outfile=$(mktemp)
        OUT_FILES+=("${outfile}")
        flash_device "${device}" >"${outfile}" 2>&1 &
        PIDS+=($!)
    done
    for i in "${!DEVICES[@]}"; do
        wait "${PIDS[i]}" && rc=0 || rc=$?
        cat "${OUT_FILES[i]}"
        rm -f "${OUT_FILES[i]}"
        [[ ${rc} -ne 0 ]] && FAILED+=("${DEVICES[i]}")
    done
else
    for device in "${DEVICES[@]}"; do
        if ! flash_device "${device}"; then
            FAILED+=("${device}")
        fi
    done
fi

echo ""
if [[ ${#FAILED[@]} -eq 0 ]]; then
    echo "==> All devices flashed successfully."
else
    echo "==> Completed with failures:" >&2
    for d in "${FAILED[@]}"; do echo "    ${d}" >&2; done
    exit 1
fi
