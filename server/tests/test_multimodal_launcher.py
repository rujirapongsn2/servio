"""Exercise the documented standalone launcher without loading model weights."""
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('port', ['8092', '8090', '8091'])
def test_documented_launcher_isolated_service(tmp_path, port):
    root = Path(__file__).resolve().parents[2]
    launcher = root / 'scripts/start-knowledge-multimodal.sh'
    model = tmp_path / 'model.gguf'
    projector = tmp_path / 'projector.gguf'
    model.touch()
    projector.touch()
    executable = tmp_path / 'fake-llama-server'
    executable.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
    executable.chmod(0o755)
    env = {**os.environ, 'LLAMA_SERVER_BIN': str(executable), 'MULTIMODAL_MODEL_PATH': str(model),
           'MULTIMODAL_MMPROJ_PATH': str(projector), 'MULTIMODAL_PORT': port, 'MULTIMODAL_THREADS': '2'}
    result = subprocess.run([str(launcher)], env=env, capture_output=True, text=True, timeout=10)
    if port in ('8090', '8091'):
        assert result.returncode != 0
        assert 'reserved for existing services' in result.stderr
        assert result.stdout == ''
    else:
        assert result.returncode == 0, result.stderr
        args = json.loads(result.stdout)
        for flag, value in {'--host': '127.0.0.1', '--port': port, '-ngl': '0', '-t': '2',
                            '-m': str(model), '--mmproj': str(projector)}.items():
            assert args[args.index(flag) + 1] == value
        assert '--embeddings' in args and '--no-mmproj-offload' in args
