"""GitHub-hosted runner client for the restricted Ubuntu endpoint."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def endpoint_module():
    spec = importlib.util.spec_from_file_location('docker_host', Path(__file__).with_name('docker_host.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connect(request, env):
    endpoint_module().validate_request(request)
    host, user, port = (env.get(name, '') for name in ('PROD_SSH_HOST', 'PROD_SSH_USER', 'PROD_SSH_PORT'))
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]*', host) or not re.fullmatch(r'[a-z_][a-z0-9_-]*', user):
        raise ValueError('Invalid SSH host/user')
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('Invalid SSH port')
    fingerprint = env.get('PROD_SSH_HOST_KEY_SHA256', '')
    if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', fingerprint):
        raise ValueError('Expected the independently verified ED25519 fingerprint')
    known_hosts = env.get('PROD_SSH_KNOWN_HOSTS', '').strip()
    # Use one explicit key; no wildcard, certificate-authority or additional trust anchors.
    fields = known_hosts.split()
    expected_host = host if port == '22' else f'[{host}]:{port}'
    if len(fields) != 3 or fields[0] != expected_host or fields[1] != 'ssh-ed25519':
        raise ValueError('known_hosts must contain only the exact target ED25519 key')
    with tempfile.TemporaryDirectory(prefix='servio-ssh-') as directory:
        root = Path(directory)
        key, hosts = root / 'key', root / 'known_hosts'
        for path, content in ((key, env['PROD_SSH_PRIVATE_KEY']), (hosts, known_hosts)):
            path.write_text(content.rstrip() + '\n')
            path.chmod(0o600)
        result = subprocess.run(['ssh-keygen', '-l', '-E', 'sha256', '-f', str(hosts)], capture_output=True, text=True, check=True)
        if result.stdout.split()[1] != fingerprint:
            raise ValueError('SSH host-key fingerprint mismatch')
        argv = ['ssh', '-F', '/dev/null', '-T', '-p', port, '-i', str(key),
                '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', f'UserKnownHostsFile={hosts}', '-o', 'GlobalKnownHostsFile=/dev/null',
                '-o', 'HostKeyAlgorithms=ssh-ed25519', '-o', 'PasswordAuthentication=no',
                '-o', 'KbdInteractiveAuthentication=no', '-o', 'ConnectTimeout=20',
                '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4',
                f'{user}@{host}', 'servio-deploy']
        result = subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True, timeout=3600)
        if result.returncode:
            raise RuntimeError('SSH/deployment failed; verify connectivity, dedicated key and protected host logs. Remote output suppressed.')
        data = json.loads(result.stdout)
        if data.get('status') not in {'ssh_verified', 'dry_run_passed', 'promoted', 'already_deployed', 'rolled_back', 'already_rolled_back'}:
            raise RuntimeError('Unexpected deployment response')
        # Print only an allowlisted summary, never raw remote output.
        return {key: data[key] for key in ('status', 'sha', 'services_changed', 'migration_executed') if key in data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['verify-ssh', 'dry-run', 'deploy', 'rollback'], required=True)
    parser.add_argument('--sha', required=True)
    args = parser.parse_args()
    images = json.loads(os.environ.get('PROD_IMAGES', '{}')) if args.mode in {'dry-run', 'deploy'} else {}
    request = {'mode': args.mode, 'sha': args.sha, 'host_id': os.environ['PROD_HOST_ID'], 'images': images}
    print(json.dumps(connect(request, os.environ)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Never echo subprocess stderr or secret-bearing input.
        raise SystemExit(f'{type(error).__name__}: SSH deployment check failed. Check settings and protected host logs.') from None
