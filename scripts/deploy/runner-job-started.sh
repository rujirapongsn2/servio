#!/bin/bash
set -eu
# Installed outside the runner checkout; executes before checkout or other steps.
[ "${GITHUB_REPOSITORY:-}" = 'rujirapongsn2/servio' ]
[ "${GITHUB_REF:-}" = 'refs/heads/main' ]
[ "${GITHUB_WORKFLOW_REF:-}" = 'rujirapongsn2/servio/.github/workflows/deploy-production.yml@refs/heads/main' ]
case "${GITHUB_EVENT_NAME:-}" in push|workflow_dispatch) ;; *) exit 1 ;; esac
printf '%s\n' 'Trusted Servio main deployment job accepted.'
