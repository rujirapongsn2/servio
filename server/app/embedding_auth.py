"""Optional, service-specific credentials for embedding requests and probes."""
import os


def headers(setting: str) -> dict[str, str]:
    key = os.getenv(setting, '').strip(' ')
    if not key:
        return {}
    if not all(33 <= ord(char) <= 126 for char in key):
        raise ValueError(f'Invalid {setting} configuration')
    return {'Authorization': 'Bearer ' + key}
