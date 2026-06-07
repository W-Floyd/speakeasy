#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") [-v variant] <device> [device...]

Flash a snapclient OTA binary extracted from the Docker image to one or more
devices sequentially.

Options:
  -v variant  sdkconfig variant to flash (default: mdns)
                available variants match snapclient-kconfig/sdkconfig.<variant>
  -h, --help  show this help

Arguments:
  device      IP address or hostname of the target device(s)
                e.g. snapclient.local  or  192.168.1.50

The script will:
  1. Build the Docker stage for the variant (uses cache if already built)
  2. Extract the OTA binary from the image
  3. Parse the firmware binary and display version/SHA256 details
  4. For each device:
     a. Read the running firmware for comparison
     b. Skip if already running the same firmware (SHA256 match)
     c. Upload via HTTP POST /api/ota/upload (falls back to TCP port 8032)
     d. Poll /api/ota/status until the device reboots and SHA256 is confirmed

For devices without the HTTP OTA endpoint (old firmware), the script
automatically falls back to the raw TCP OTA server on port 8032.
EOF
    exit 1
}

# ── Arg parsing ───────────────────────────────────────────────────────────────

VARIANT="mdns"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v) VARIANT="${2:?-v requires a variant argument}"; shift 2 ;;
        -h|--help) usage ;;
        *) break ;;
    esac
done

[[ $# -lt 1 ]] && usage

DEVICES=("$@")
STAGE="snapclient-${VARIANT}"
OTA_BIN="${STAGE}-ota.bin"
IMAGE_TAG="speakeasy-${STAGE}-extract"

# ── Helpers ───────────────────────────────────────────────────────────────────

parse_app_desc() {
    python3 - "$1" <<'EOF'
import sys, struct

data = open(sys.argv[1], 'rb').read()
magic_bytes = struct.pack('<I', 0xABCD5432)
pos = data.find(magic_bytes)
if pos < 0:
    print('ERROR: esp_app_desc_t magic not found', file=sys.stderr)
    sys.exit(1)

def cstr(off, length):
    s = data[pos+off : pos+off+length]
    return s[:s.find(b'\x00')].decode('utf-8', errors='replace')

print(f"version={cstr(16, 32)}")
print(f"project_name={cstr(48, 32)}")
print(f"compile_date={cstr(96, 16)}")
print(f"compile_time={cstr(80, 16)}")
print(f"idf_version={cstr(112, 32)}")
print(f"sha256={data[pos+144:pos+176].hex()}")
EOF
}

dev_status_json() {
    curl -sf --max-time 3 "http://$1/api/ota/status" 2>/dev/null || true
}

json_field() {
    echo "$1" | grep -o "\"$2\":\"[^\"]*\"" | grep -o '[^"]*$' || true
}

# ── Flash one device; returns 0 on success, 1 on failure ─────────────────────

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

    echo "==> Uploading to http://${device}/api/ota/upload..."
    local http_ota=0
    if curl -fS \
        -X POST \
        "http://${device}/api/ota/upload" \
        -H "Expect:" \
        -H "Content-Type: application/octet-stream" \
        --data-binary @"${TMP}"; then
        http_ota=1
    else
        echo "    HTTP OTA failed; falling back to TCP OTA on port 8032..."
        if ! curl -S -H "Expect:" "${device}:8032" --data-binary @"${TMP}"; then
            echo "==> ERROR: both OTA methods failed for ${device}" >&2
            return 1
        fi
    fi

    echo ""
    echo "==> Upload complete. Waiting for device to reboot..."

    if [[ "${http_ota}" -eq 0 ]]; then
        echo "    Done (TCP OTA — no reboot confirmation available)."
        return 0
    fi

    if [[ "${has_status}" -eq 0 ]]; then
        echo "    Done."
        return 0
    fi

    local timeout=60 elapsed=0 new_json new_sha
    while [[ ${elapsed} -lt ${timeout} ]]; do
        sleep 2; elapsed=$((elapsed + 2))
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

# ── Build + extract ───────────────────────────────────────────────────────────

echo "==> Building stage ${STAGE} (uses cache if already built)..."
docker build --target "${STAGE}" -t "${IMAGE_TAG}" \
    "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

echo "==> Extracting ${OTA_BIN}..."
TMP=$(mktemp)
trap 'rm -f "${TMP}"' EXIT

CONTAINER=$(docker create "${IMAGE_TAG}")
docker cp "${CONTAINER}:/output/${STAGE}/${OTA_BIN}" "${TMP}"
docker rm "${CONTAINER}" > /dev/null

echo "==> Parsing firmware binary..."
APP_DESC=$(parse_app_desc "${TMP}")
BIN_SHA=$(echo "${APP_DESC}" | grep '^sha256='       | cut -d= -f2)
BIN_VER=$(echo "${APP_DESC}" | grep '^version='      | cut -d= -f2)
BIN_NAME=$(echo "${APP_DESC}" | grep '^project_name='| cut -d= -f2)
BIN_DATE=$(echo "${APP_DESC}" | grep '^compile_date=' | cut -d= -f2)
BIN_TIME=$(echo "${APP_DESC}" | grep '^compile_time=' | cut -d= -f2)
BIN_IDF=$(echo "${APP_DESC}" | grep '^idf_version='  | cut -d= -f2)

echo ""
echo "  Binary to flash:"
echo "    project : ${BIN_NAME}"
echo "    version : ${BIN_VER}"
echo "    built   : ${BIN_DATE} ${BIN_TIME}"
echo "    IDF     : ${BIN_IDF}"
echo "    sha256  : ${BIN_SHA}"

# ── Flash each device ─────────────────────────────────────────────────────────

FAILED=()
for device in "${DEVICES[@]}"; do
    if ! flash_device "${device}"; then
        FAILED+=("${device}")
    fi
done

echo ""
if [[ ${#FAILED[@]} -eq 0 ]]; then
    echo "==> All devices flashed successfully."
else
    echo "==> Completed with failures:" >&2
    for d in "${FAILED[@]}"; do echo "    ${d}" >&2; done
    exit 1
fi
