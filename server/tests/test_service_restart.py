import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("all", ["up -d --force-recreate"]),
        ("backend", ["up -d --force-recreate --no-deps backend", "restart nginx"]),
        ("frontend", ["up -d --force-recreate --no-deps frontend", "restart nginx"]),
        ("postgres", ["up -d --force-recreate --no-deps postgres"]),
        ("nginx", ["up -d --force-recreate --no-deps nginx"]),
    ],
)
def test_restart_applies_current_environment(tmp_path, target, expected):
    source = Path(__file__).resolve().parents[2] / "services.sh"
    script = tmp_path / "services.sh"
    script.write_text(source.read_text().removesuffix('main "$@"\n'))
    result = subprocess.run(
        [
            "bash", "-c",
            '''source "$1"
check_docker() { :; }
ensure_env() { :; }
generate_certs() { :; }
ensure_data_permissions() { :; }
info() { :; }
show_urls() { :; }
run_compose() { echo "$*" >> compose.log; }
cmd_restart "$2"
cat compose.log
''',
            "test-restart", str(script), target,
        ],
        text=True, capture_output=True, check=True,
    )
    assert result.stdout.splitlines() == expected
