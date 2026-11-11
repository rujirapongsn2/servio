#!/bin/sh
# Root-owned forced-command wrapper; no interactive shell, upload or port forwarding.
set -eu
[ "${SSH_ORIGINAL_COMMAND:-}" = servio-deploy ] || exit 126
exec sudo -n /usr/bin/python3 -I /usr/local/lib/servio-deploy/docker_host.py
