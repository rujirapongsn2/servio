#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from uuid import uuid4

from dotenv import dotenv_values, set_key


def checksum(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def wait_ready(bind, port, key, profile):
    deadline = time.monotonic() + 60
    host = {'0.0.0.0': '127.0.0.1', '::': '::1'}.get(bind, bind)
    authority = f'[{host}]' if ':' in host else host
    request = Request(f'http://{authority}:{port}/health',
                      headers={'Authorization': 'Bearer ' + key})
    while time.monotonic() < deadline:
        try:
            with urlopen(request, timeout=1) as response:
                data = json.load(response)
            if data.get('ready') and data.get('profile') == profile:
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError('Installed service did not become ready; inspect native logs')


def install():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('Run with native Apple Silicon Python on macOS')
    repo = Path(__file__).resolve().parents[1]
    runtime = Path.home() / 'Library/Application Support/Servio/IntentDecision'
    label = 'ai.softnix.servio.intent-decision'
    agent = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
    settings = dotenv_values(repo / '.env')
    key = settings.get('INTENT_DECISION_API_KEY', '')
    if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise SystemExit('Set a valid dedicated INTENT_DECISION_API_KEY first')
    source_model = Path(settings.get('INTENT_DECISION_MODEL_PATH') or
                        repo / 'server/decision_service/models/embeddinggemma-2-text-270m.litertlm')
    if not source_model.is_absolute():
        source_model = repo / 'server' / source_model
    sys.path.insert(0, str(repo / 'server'))
    from app.intent_contract import DECISION_MODEL_SHA256, DECISION_PROFILE
    if checksum(source_model) != DECISION_MODEL_SHA256:
        raise SystemExit('Model checksum does not match the tested profile')
    uv = shutil.which('uv')
    if not uv:
        raise SystemExit('Install uv before installing the native runtime')
    marker = runtime / 'deployment.json'
    if marker.exists() and json.loads(marker.read_text()).get('source_repo') != str(repo):
        raise SystemExit('Runtime belongs to another checkout; inspect it before replacing it')
    domain = f'gui/{os.getuid()}'
    loaded = subprocess.run(['launchctl', 'print', f'{domain}/{label}'], capture_output=True).returncode == 0
    old_bytes = agent.read_bytes() if agent.exists() else None
    if old_bytes:
        old = plistlib.loads(old_bytes)
        args = old.get('ProgramArguments', [])
        old_script = Path(args[0]) if len(args) == 1 else None
        owned_release = (old_script is not None and old_script.name == 'run_intent_decision.sh'
                         and old_script.parent.name == 'scripts'
                         and old_script.parent.parent.parent == runtime / 'releases')
        owned_legacy = args in [[str(repo / 'scripts/run_intent_decision.sh')],
                               [str(runtime / 'scripts/run_intent_decision.sh')]]
        if old.get('Label') != label or not (owned_release or owned_legacy):
            raise SystemExit('Existing LaunchAgent belongs to another installation')
    elif loaded:
        raise SystemExit('A job with this label is already loaded elsewhere')
    runtime.mkdir(parents=True, exist_ok=True)
    runtime.chmod(0o700)
    release = runtime / 'releases' / uuid4().hex
    release.mkdir(parents=True)
    files = ['scripts/run_intent_decision.sh', 'server/decision_service/__init__.py',
             'server/decision_service/service.py', 'server/decision_service/requirements.txt',
             'server/app/intent_contract.py']
    for relative in files:
        target = release / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / relative, target)
    (release / 'scripts/run_intent_decision.sh').chmod(0o755)
    (release / 'server/app/__init__.py').write_text('')
    model = release / 'server/decision_service/models' / source_model.name
    model.parent.mkdir()
    shutil.copyfile(source_model, model)
    config = release / '.env'
    port = settings.get('INTENT_DECISION_PORT') or '8095'
    bind = settings.get('INTENT_DECISION_BIND') or '127.0.0.1'
    for name, value in {
        'INTENT_DECISION_API_KEY': key, 'INTENT_DECISION_MODEL_PATH': str(model),
        'INTENT_DECISION_BIND': bind,
        'INTENT_DECISION_PORT': port,
    }.items():
        set_key(config, name, value)
    config.chmod(0o600)
    venv = release / 'server/decision_service/.venv'
    subprocess.run([uv, 'venv', '--python', '3.11', str(venv)], check=True)
    subprocess.run([uv, 'pip', 'install', '--python', str(venv / 'bin/python'), '-r',
                    str(release / 'server/decision_service/requirements.txt')], check=True)
    cache = release / 'server/decision_service/.cache'
    cache.mkdir(exist_ok=True)
    subprocess.run([str(venv / 'bin/python'), '-c',
                    'import mediapipe; import decision_service.service'],
                   cwd=release / 'server', check=True,
                   env={**os.environ, 'MPLCONFIGDIR': str(cache / 'matplotlib'),
                        'XDG_CACHE_HOME': str(cache)})
    job = {
        'Label': label, 'ProgramArguments': [str(release / 'scripts/run_intent_decision.sh')],
        'WorkingDirectory': str(release), 'RunAtLoad': True,
        'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': 30, 'ProcessType': 'Background',
        'EnvironmentVariables': {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin',
                                 'PYTHONUNBUFFERED': '1', 'XDG_CACHE_HOME': str(cache)},
        'StandardOutPath': str(cache / 'service.stdout.log'),
        'StandardErrorPath': str(cache / 'service.stderr.log'),
    }
    agent.parent.mkdir(exist_ok=True)
    if loaded:
        subprocess.run(['launchctl', 'bootout', domain, str(agent)], check=True)
    try:
        agent.write_bytes(plistlib.dumps(job))
        agent.chmod(0o600)
        subprocess.run(['launchctl', 'bootstrap', domain, str(agent)], check=True)
        wait_ready(bind, port, key, DECISION_PROFILE)
    except BaseException:
        subprocess.run(['launchctl', 'bootout', domain, str(agent)], capture_output=True)
        if old_bytes:
            agent.write_bytes(old_bytes)
            agent.chmod(0o600)
            if loaded:
                subprocess.run(['launchctl', 'bootstrap', domain, str(agent)], check=True)
        else:
            agent.unlink(missing_ok=True)
        raise
    marker.write_text(json.dumps({'source_repo': str(repo), 'release': str(release),
        'source_hashes': {relative: checksum(repo / relative) for relative in files}}, indent=2))
    print('Native Intent Decision Maker installed, ready and configured for user login')
    print(f'Runtime release: {release}')


if __name__ == '__main__':
    install()
