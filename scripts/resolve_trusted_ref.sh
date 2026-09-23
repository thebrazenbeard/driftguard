#!/usr/bin/env bash
set -euo pipefail

: "${DG_TRUST_INPUT:?DG_TRUST_INPUT is required}"
: "${DG_EVENT_NAME:?DG_EVENT_NAME is required}"

trust="${DG_TRUST_INPUT}"

if [ "${trust}" != "auto" ]; then
  printf '%s\n' "${trust}"
  exit 0
fi

if [ "${DG_EVENT_NAME}" = "pull_request" ]; then
  if [ -z "${DG_PR_BASE_SHA:-}" ]; then
    echo "DriftGuard auto trust cannot establish the pull-request base commit." >&2
    exit 2
  fi
  printf '%s\n' "${DG_PR_BASE_SHA}"
  exit 0
fi

if [ "${DG_EVENT_NAME}" = "push" ]; then
  zero="0000000000000000000000000000000000000000"
  if [ -n "${DG_PUSH_BEFORE_SHA:-}" ] && [ "${DG_PUSH_BEFORE_SHA}" != "${zero}" ]; then
    printf '%s\n' "${DG_PUSH_BEFORE_SHA}"
    exit 0
  fi

  if [ -z "${DG_CURRENT_SHA:-}" ]; then
    echo "DriftGuard auto trust cannot resolve a push without github.sha." >&2
    exit 2
  fi

  if ! git cat-file -e "${DG_CURRENT_SHA}^" 2>/dev/null; then
    git fetch --no-tags --deepen=1 origin >&2 || true
  fi

  if ! parent="$(git rev-parse "${DG_CURRENT_SHA}^" 2>/dev/null)"; then
    echo "DriftGuard auto trust cannot establish pre-change Git state. Use trusted-ref=workspace only for an explicit bootstrap." >&2
    exit 2
  fi

  printf '%s\n' "${parent}"
  exit 0
fi

printf '%s\n' "workspace"
