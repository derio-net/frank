#!/usr/bin/env bash
#
# rename-nodes.sh — Rename Talos v1.12+ nodes in an Omni-managed cluster
#
# Talos v1.12 uses a separate HostnameConfig document (not machine.network.hostname).
# This script applies per-machine HostnameConfig patches via Omni ConfigPatch resources,
# ONE NODE AT A TIME, with health verification between each.
#
# Prerequisites:
#   - omnictl configured and authenticated
#   - source ../.env (for CLUSTER_NAME and node IPs)
#
# Usage:
#   source ../.env
#   ./scripts/rename-nodes.sh <command>
#
set -euo pipefail

CLUSTER="${CLUSTER_NAME:-frank}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/../.rename-work"
MAPPING_FILE="${WORK_DIR}/machine-hostname-mapping.env"
LABELS_BACKUP="${WORK_DIR}/labels-backup.yaml"
PATCHES_DIR="${WORK_DIR}/patches"

mkdir -p "${WORK_DIR}" "${PATCHES_DIR}"

# ─── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
err()   { echo -e "${RED}[ERR]${NC}   $*" >&2; }

# ─── Helpers ───────────────────────────────────────────────────────

# Wait for a specific machine to be READY in Omni
wait_machine_ready() {
    local machine_id="$1"
    local timeout="${2:-120}"
    local elapsed=0

    info "  Waiting for ${machine_id} to become READY (timeout: ${timeout}s)..."
    while (( elapsed < timeout )); do
        local ready
        ready=$(omnictl get clustermachinestatus "${machine_id}" -o yaml 2>/dev/null \
            | awk '/ready:/ {print $2; exit}' || echo "false")
        if [[ "${ready}" == "true" ]]; then
            ok "  Machine is READY after ${elapsed}s"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        printf "."
    done
    echo ""
    err "  Machine ${machine_id} did not become READY within ${timeout}s"
    return 1
}

# Wait for cluster to be healthy (all machines READY, no Reconfiguring)
wait_cluster_healthy() {
    local timeout="${1:-180}"
    local elapsed=0

    info "Waiting for cluster '${CLUSTER}' to be fully healthy (timeout: ${timeout}s)..."
    while (( elapsed < timeout )); do
        local all_ready=true
        while IFS= read -r line; do
            local ready
            ready=$(echo "${line}" | awk '{print $6}')
            if [[ "${ready}" != "true" ]]; then
                all_ready=false
                break
            fi
        done < <(omnictl get clustermachinestatus -l omni.sidero.dev/cluster="${CLUSTER}" --no-headers 2>/dev/null)

        if ${all_ready}; then
            ok "All machines READY after ${elapsed}s"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        printf "."
    done
    echo ""
    err "Cluster did not become fully healthy within ${timeout}s"
    return 1
}

# Read the mapping file into HOSTNAME_MAP associative array
load_mapping() {
    declare -gA HOSTNAME_MAP
    HOSTNAME_MAP=()

    if [[ ! -f "${MAPPING_FILE}" ]]; then
        err "Mapping file not found: ${MAPPING_FILE}"
        err "Run '$0 discover' and '$0 generate-mapping' first."
        exit 1
    fi

    while IFS='=' read -r machine_id hostname; do
        hostname="${hostname%%#*}"
        hostname="${hostname// /}"
        machine_id="${machine_id// /}"
        [[ -z "${machine_id}" || "${machine_id}" =~ ^# ]] && continue
        [[ "${hostname}" == "FILL_IN_HOSTNAME" ]] && continue
        HOSTNAME_MAP["${machine_id}"]="${hostname}"
    done < "${MAPPING_FILE}"

    if [[ ${#HOSTNAME_MAP[@]} -eq 0 ]]; then
        err "No valid mappings found in ${MAPPING_FILE}."
        exit 1
    fi
}

# ─── Step 1: Discover ─────────────────────────────────────────────
cmd_discover() {
    info "Discovering machines in cluster '${CLUSTER}'..."
    echo ""

    info "Machines registered in Omni:"
    omnictl get machines -o yaml > "${WORK_DIR}/machines-raw.yaml"
    omnictl get machines
    echo ""

    info "Cluster machine statuses:"
    omnictl get clustermachinestatus -l omni.sidero.dev/cluster="${CLUSTER}" -o yaml \
        > "${WORK_DIR}/clustermachinestatus-raw.yaml" 2>/dev/null || true
    omnictl get clustermachinestatus -l omni.sidero.dev/cluster="${CLUSTER}" 2>/dev/null || true
    echo ""

    info "Machine labels:"
    omnictl get machinelabels -o yaml > "${WORK_DIR}/machinelabels-raw.yaml" 2>/dev/null || true
    omnictl get machinelabels 2>/dev/null || true
    echo ""

    info "Existing config patches for cluster '${CLUSTER}':"
    omnictl get configpatch -l omni.sidero.dev/cluster="${CLUSTER}" -o yaml \
        > "${WORK_DIR}/configpatches-raw.yaml" 2>/dev/null || true
    omnictl get configpatch -l omni.sidero.dev/cluster="${CLUSTER}" 2>/dev/null || true
    echo ""

    info "Raw data saved to ${WORK_DIR}/"
    info ""
    info "Next: $0 generate-mapping"
}

# ─── Step 1b: Generate mapping template ───────────────────────────
cmd_generate_mapping() {
    if [[ ! -f "${WORK_DIR}/machines-raw.yaml" ]]; then
        err "Run '$0 discover' first."
        exit 1
    fi

    info "Generating mapping template..."

    cat > "${MAPPING_FILE}" <<'HEADER'
# Machine ID → Desired Hostname mapping
#
# Format: MACHINE_ID=desired-hostname
#
# Example:
#   abc12345-def6-7890-abcd-ef1234567890=frank-mini-1
#
HEADER

    local machine_ids
    machine_ids=$(awk '/^[[:space:]]+id:/ {gsub(/"/, "", $2); print $2}' "${WORK_DIR}/machines-raw.yaml" || true)

    if [[ -z "${machine_ids}" ]]; then
        warn "Could not parse machine IDs. Trying table output..."
        omnictl get machines --no-headers 2>/dev/null | awk '{print $2}' | while read -r mid; do
            echo "${mid}=FILL_IN_HOSTNAME  # TODO"
        done >> "${MAPPING_FILE}"
    else
        for mid in ${machine_ids}; do
            local current_hostname
            current_hostname=$(grep -A5 "id: ${mid}" "${WORK_DIR}/clustermachinestatus-raw.yaml" 2>/dev/null \
                | awk -F: '/hostname:/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' \
                || echo "unknown")
            [[ -z "${current_hostname}" ]] && current_hostname="unknown"
            echo "${mid}=${current_hostname}  # current: ${current_hostname} — CHANGE THIS"
        done >> "${MAPPING_FILE}"
    fi

    ok "Mapping template: ${MAPPING_FILE}"
    info "Edit it, then run: $0 backup && $0 rename"
}

# ─── Step 2: Backup labels ────────────────────────────────────────
cmd_backup() {
    info "Backing up all machine labels..."
    omnictl get machinelabels -o yaml > "${LABELS_BACKUP}"
    ok "Labels backed up to ${LABELS_BACKUP}"
}

# ─── Step 3: Rename — one node at a time ──────────────────────────
cmd_rename() {
    load_mapping

    info "Hostname mappings loaded (${#HOSTNAME_MAP[@]} nodes):"
    local index=0
    local ordered_ids=()
    for mid in "${!HOSTNAME_MAP[@]}"; do
        index=$((index + 1))
        echo "  ${index}. ${mid} → ${HOSTNAME_MAP[${mid}]}"
        ordered_ids+=("${mid}")
    done
    echo ""

    info "Nodes will be renamed ONE AT A TIME with health checks."
    info "You will be prompted before each node."
    echo ""

    local success_count=0
    local total=${#ordered_ids[@]}

    for mid in "${ordered_ids[@]}"; do
        local desired="${HOSTNAME_MAP[${mid}]}"
        local patch_id="900-hostname-${mid}"
        local patch_file="${PATCHES_DIR}/configpatch-${desired}.yaml"

        echo ""
        info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        info "Node $((success_count + 1))/${total}: ${mid} → ${desired}"
        info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        read -rp "Apply this rename? (y/N/q=quit) " answer
        case "${answer}" in
            [Qq]*) info "Stopped. ${success_count}/${total} nodes renamed."; return 0 ;;
            [Yy]*)  ;;
            *)      info "Skipping ${desired}."; continue ;;
        esac

        # Create the ConfigPatch resource with HostnameConfig document
        # Talos v1.12+ requires HostnameConfig with auto: off to override stable hostname
        info "  Creating HostnameConfig patch..."
        cat > "${patch_file}" <<RESOURCE
metadata:
  namespace: default
  type: ConfigPatches.omni.sidero.dev
  id: ${patch_id}
  labels:
    omni.sidero.dev/cluster: ${CLUSTER}
    omni.sidero.dev/cluster-machine: ${mid}
spec:
  data: |
    apiVersion: v1alpha1
    kind: HostnameConfig
    hostname: ${desired}
    auto: off
RESOURCE

        info "  Applying patch '${patch_id}'..."
        if ! omnictl apply -f "${patch_file}"; then
            err "  Failed to apply patch for ${desired}!"
            read -rp "  Continue with next node? (y/N) " cont
            [[ "${cont}" =~ ^[Yy] ]] || return 1
            continue
        fi
        ok "  Patch applied."

        # Wait for this machine to reconfigure and become ready
        if ! wait_machine_ready "${mid}" 120; then
            warn "  Machine did not become READY. Rolling back this patch..."
            omnictl delete configpatch "${patch_id}" 2>/dev/null || true
            err "  Patch rolled back for ${desired}."
            read -rp "  Continue with next node? (y/N) " cont
            [[ "${cont}" =~ ^[Yy] ]] || return 1
            continue
        fi

        # Verify hostname actually changed
        sleep 3  # brief settle time
        local actual_hostname="unknown"
        actual_hostname=$(omnictl get clustermachineconfigstatus "${mid}" -o yaml 2>/dev/null \
            | awk '/hostname:/ {gsub(/^[[:space:]]+|[[:space:]]+$|"/, "", $2); print $2; exit}' || echo "unknown")

        if [[ "${actual_hostname}" == "${desired}" ]]; then
            ok "  Hostname verified: ${desired}"
        else
            warn "  Expected '${desired}' but got '${actual_hostname}'"
            warn "  The patch is applied — hostname may need more time or a reboot."
            read -rp "  Keep patch and continue? (y=keep/r=rollback/q=quit) " action
            case "${action}" in
                [Rr]*)
                    omnictl delete configpatch "${patch_id}" 2>/dev/null || true
                    warn "  Patch rolled back for ${desired}."
                    continue
                    ;;
                [Qq]*) return 1 ;;
            esac
        fi

        success_count=$((success_count + 1))
        ok "  Progress: ${success_count}/${total} nodes renamed."
    done

    echo ""
    ok "Rename complete: ${success_count}/${total} nodes processed."
    info "Run '$0 verify' to confirm all hostnames."
}

# ─── Step 4: Verify ───────────────────────────────────────────────
cmd_verify() {
    info "Verifying hostnames after rename..."
    echo ""

    info "Cluster machine statuses:"
    omnictl get clustermachinestatus -l omni.sidero.dev/cluster="${CLUSTER}" 2>/dev/null || true
    echo ""

    info "Machine labels (should persist across rename):"
    omnictl get machinelabels 2>/dev/null || true
    echo ""

    # Check via talosctl if available
    if command -v talosctl &>/dev/null; then
        info "Talos node hostnames:"
        for ip in ${CONTROL_PLANE_IP_1:-} ${CONTROL_PLANE_IP_2:-} ${CONTROL_PLANE_IP_3:-} \
                  ${RASPI_1:-} ${RASPI_2:-} ${GPU_1:-} ${PC_1:-}; do
            [[ -z "${ip}" ]] && continue
            local hn
            hn=$(talosctl get hostname -n "${ip}" -o json 2>/dev/null \
                | jq -r '.spec.hostname' 2>/dev/null || echo "unreachable")
            echo "  ${ip} → ${hn}"
        done
    fi

    echo ""
    info "If labels are missing, restore with:"
    info "  omnictl apply -f ${LABELS_BACKUP}"
}

# ─── Step 5: Rollback ─────────────────────────────────────────────
cmd_rollback() {
    warn "Rolling back hostname patches..."
    echo ""

    load_mapping 2>/dev/null || true

    # Delete all hostname patches by ID
    for mid in "${!HOSTNAME_MAP[@]}"; do
        local patch_id="900-hostname-${mid}"
        info "  Deleting: ${patch_id}"
        omnictl delete configpatch "${patch_id}" 2>/dev/null && \
            ok "    Deleted" || \
            warn "    Not found or already deleted"
    done

    echo ""
    ok "All hostname patches removed."
    info "Waiting for cluster to stabilize..."
    wait_cluster_healthy 180 || warn "Cluster may still be settling — check Omni UI."
}

# ─── Rename a single node by hostname ─────────────────────────────
cmd_rename_one() {
    local target="${2:-}"
    if [[ -z "${target}" ]]; then
        err "Usage: $0 rename-one <desired-hostname>"
        err "Example: $0 rename-one mini-1"
        exit 1
    fi

    load_mapping

    local target_mid=""
    for mid in "${!HOSTNAME_MAP[@]}"; do
        if [[ "${HOSTNAME_MAP[${mid}]}" == "${target}" ]]; then
            target_mid="${mid}"
            break
        fi
    done

    if [[ -z "${target_mid}" ]]; then
        err "Hostname '${target}' not found in mapping file."
        exit 1
    fi

    local patch_id="900-hostname-${target_mid}"
    local patch_file="${PATCHES_DIR}/configpatch-${target}.yaml"

    info "Renaming ${target_mid} → ${target}"

    cat > "${patch_file}" <<RESOURCE
metadata:
  namespace: default
  type: ConfigPatches.omni.sidero.dev
  id: ${patch_id}
  labels:
    omni.sidero.dev/cluster: ${CLUSTER}
    omni.sidero.dev/cluster-machine: ${target_mid}
spec:
  data: |
    apiVersion: v1alpha1
    kind: HostnameConfig
    hostname: ${target}
    auto: off
RESOURCE

    omnictl apply -f "${patch_file}" || { err "Failed to apply patch."; exit 1; }
    ok "Patch applied."

    wait_machine_ready "${target_mid}" 120
    info "Run '$0 verify' to confirm."
}

# ─── Main ──────────────────────────────────────────────────────────
case "${1:-help}" in
    discover)         cmd_discover ;;
    generate-mapping) cmd_generate_mapping ;;
    backup)           cmd_backup ;;
    rename)           cmd_rename ;;
    rename-one)       cmd_rename_one "$@" ;;
    verify)           cmd_verify ;;
    rollback)         cmd_rollback ;;
    help|*)
        echo "Usage: $0 <command> [args]"
        echo ""
        echo "Commands:"
        echo "  discover          Collect current machine IDs, hostnames, labels"
        echo "  generate-mapping  Create a mapping file to fill in desired hostnames"
        echo "  backup            Back up all machine labels"
        echo "  rename            Apply hostname patches ONE NODE AT A TIME"
        echo "  rename-one <name> Rename a single node by its desired hostname"
        echo "  verify            Check that renames took effect and labels persist"
        echo "  rollback          Remove all hostname patches"
        echo ""
        echo "Workflow:"
        echo "  source .env"
        echo "  $0 discover"
        echo "  $0 generate-mapping"
        echo "  # Edit .rename-work/machine-hostname-mapping.env"
        echo "  $0 backup"
        echo "  $0 rename            # interactive, one node at a time"
        echo "  $0 rename-one mini-1 # or target a single node"
        echo "  $0 verify"
        ;;
esac
