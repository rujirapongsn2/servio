"""Record the existing native deployment without restarting any service."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def bootstrap(root, previous_path, directory):
    os.umask(0o077)
    previous = json.loads(previous_path.read_text())
    config = json.loads(Path(__file__).with_name('production.example.json').read_text())
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    locations = {'root': root, 'env_file': root / '.env', 'state_file': directory / 'state.json',
                 'release_dir': directory / 'releases', 'log_dir': directory / 'logs',
                 'backup_dir': directory / 'backups', 'shared_data': root / 'server/data'}
    config.update({key: str(value) for key, value in locations.items()})
    config.update({key: shutil.which(key) for key in ('node', 'npm', 'uv')})
    if not all(config[key] for key in ('node', 'npm', 'uv')):
        raise SystemExit('node, npm and uv must be installed on the deployment host')
    state = {'components': {}}
    for kind, port in config['ports'].items():
        pid = previous[kind]['pid']
        listeners = subprocess.check_output(['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'], text=True).split()
        if listeners != [str(pid)]:
            raise SystemExit('Production process changed; inspect before recording rollback state')
        source = Path(previous[kind + '_snapshot'])
        cwd = source / ('server' if kind == 'backend' else 'frontend')
        if kind == 'backend':
            command = [str(root / 'server/.venv/bin/python'), '-B', '-m', 'uvicorn', 'server:app',
                       '--host', '127.0.0.1', '--port', str(port), '--no-access-log']
        else:
            command = [config['node'], str(root / 'frontend/node_modules/next/dist/bin/next'),
                       'start', '--hostname', '127.0.0.1', '--port', str(port)]
        state['components'][kind] = {'pid': pid, 'sha': previous[kind + '_commit'], 'source': str(source),
                                     'cwd': str(cwd), 'command': command, 'port': port}
    outputs = ((directory / 'config.json', config), (directory / 'state.json', state))
    if any(path.exists() for path, _ in outputs):
        raise SystemExit('Deployment config/state already exists; refusing to overwrite')
    for path, value in outputs:
        with path.open('x') as stream:
            os.chmod(path, 0o600); json.dump(value, stream, indent=2)
    print('Recorded deployment config and rollback state; no services restarted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--previous-state', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    bootstrap(args.root.resolve(), args.previous_state.resolve(), args.directory.resolve())
