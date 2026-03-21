#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DOCKER_IMAGE="${MEMORY_PALACE_PWSH_DOCKER_IMAGE:-mcr.microsoft.com/powershell:7.4-ubuntu-22.04}"
SMOKE_DIR="${PROJECT_ROOT}/.tmp/pwsh-docker-smoke"
KEEP_OUTPUT=1

usage() {
  cat <<'EOF'
Usage:
  bash scripts/smoke_apply_profile_ps1_in_docker.sh [--image <docker-image>] [--no-keep-output]

What it does:
  - Runs apply_profile.ps1 inside a PowerShell Docker image
  - Smokes the Linux local profile path
  - Smokes the Docker profile path
  - Verifies the generated env files on the host

Environment:
  MEMORY_PALACE_PWSH_DOCKER_IMAGE   Override the PowerShell image
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      [[ $# -ge 2 ]] || { echo "Missing value for --image" >&2; exit 2; }
      DOCKER_IMAGE="$2"
      shift 2
      ;;
    --no-keep-output)
      KEEP_OUTPUT=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for pwsh-in-docker smoke." >&2
  exit 1
fi

mkdir -p "${SMOKE_DIR}"
linux_target=".tmp/pwsh-docker-smoke/linux-profile-b.env"
docker_target=".tmp/pwsh-docker-smoke/docker-profile-b.env"

cleanup() {
  if [[ "${KEEP_OUTPUT}" -eq 0 ]]; then
    rm -rf "${SMOKE_DIR}"
  fi
}
trap cleanup EXIT

pwsh_command=$(
  cat <<EOF
& './scripts/apply_profile.ps1' -Platform linux -Profile b -Target '${linux_target}';
& './scripts/apply_profile.ps1' -Platform docker -Profile b -Target '${docker_target}';
EOF
)

docker run --rm \
  --mount "type=bind,src=${PROJECT_ROOT},dst=${PROJECT_ROOT}" \
  -w "${PROJECT_ROOT}" \
  "${DOCKER_IMAGE}" \
  pwsh -NoLogo -NoProfile -Command "${pwsh_command}"

linux_env_path="${PROJECT_ROOT}/${linux_target}"
docker_env_path="${PROJECT_ROOT}/${docker_target}"

[[ -f "${linux_env_path}" ]] || { echo "Missing generated file: ${linux_env_path}" >&2; exit 1; }
[[ -f "${docker_env_path}" ]] || { echo "Missing generated file: ${docker_env_path}" >&2; exit 1; }

expected_linux_url="DATABASE_URL=sqlite+aiosqlite:////${PROJECT_ROOT#/}/demo.db"
if ! grep -Fxq "${expected_linux_url}" "${linux_env_path}"; then
  echo "Unexpected Linux DATABASE_URL in ${linux_env_path}" >&2
  exit 1
fi

if ! grep -Eq '^MCP_API_KEY=.+$' "${docker_env_path}"; then
  echo "Docker smoke did not generate MCP_API_KEY in ${docker_env_path}" >&2
  exit 1
fi

if ! grep -Fxq 'SEARCH_DEFAULT_MODE=hybrid' "${linux_env_path}"; then
  echo "Linux smoke output is missing SEARCH_DEFAULT_MODE=hybrid" >&2
  exit 1
fi

printf '%s\n' "[pwsh-docker-smoke] PASS"
printf '%s\n' "  image: ${DOCKER_IMAGE}"
printf '%s\n' "  linux env: ${linux_env_path}"
printf '%s\n' "  docker env: ${docker_env_path}"
