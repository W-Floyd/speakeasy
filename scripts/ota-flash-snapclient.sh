#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") [-v variant] [-p] <device> [device...]

Flash a snapclient OTA binary extracted from the Docker image to one or more
devices.

Options:
  -v variant      sdkconfig variant to flash (default: mdns)
                    available variants match snapclient-kconfig/sdkconfig.<variant>
  -p, --parallel  flash all devices concurrently (default: sequential)
  -h, --help      show this help

Arguments:
  device      IP address or hostname of the target device(s)
                e.g. snapclient.local  or  192.168.1.50
                HTTP server is expected on port 8000

The script will:
  1. Build the Docker stage for the variant (uses cache if already built)
  2. Extract the OTA binary from the image
  3. Parse the firmware binary and display version/SHA256 details
  4. For each device:
     a. Read the running firmware for comparison
     b. Skip if already running the same firmware (SHA256 match)
     c. Upload via HTTP POST /api/ota/upload
     d. Poll /api/ota/status until the device reboots and SHA256 is confirmed
EOF
    exit 1
}

# ── Arg parsing ───────────────────────────────────────────────────────────────

VARIANT="mdns"
PARALLEL=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v) VARIANT="${2:?-v requires a variant argument}"; shift 2 ;;
        -p|--parallel) PARALLEL=1; shift ;;
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
    python3 -m esptool image-info "$1" 2>/dev/null
}

dev_status_json() {
    curl -sf --max-time 3 "http://$1:8000/api/ota/status" 2>/dev/null || true
}

json_field() {
    echo "$1" | jq -r --arg k "$2" '.[$k] // empty'
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

# ── Flash each device ────────────────────────────────────────────────────────

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
