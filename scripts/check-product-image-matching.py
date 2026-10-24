"""Verify category-aware product search through the widget WebSocket protocol."""
import argparse
import asyncio
import base64
import hashlib
import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

import httpx
import websockets


async def check_case(client, base, key, case, directory, origin):
    data = (directory / case['image']).read_bytes()
    if not 0 < len(data) <= 10 * 1024 * 1024:
        raise ValueError('Fixture exceeds image byte limit')
    if data.startswith(b'\x89PNG'):
        mime = 'image/png'
    elif data.startswith(b'\xff\xd8'):
        mime = 'image/jpeg'
    else:
        raise ValueError('Use a real JPG or PNG fixture')
    request_id = 'verify_' + uuid.uuid4().hex
    socket_url = base.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/ws?' + urlencode({'api_key': key})
    started = time.monotonic()
    async with websockets.connect(socket_url, origin=origin,
                                  max_size=32 * 1024 * 1024, open_timeout=15) as socket:
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), 60))
            if event.get('type') == 'session.config':
                if not event.get('knowledge_image_search_enabled'):
                    raise ValueError('Widget image search is not enabled')
                break
        await socket.send(json.dumps({'type': 'knowledge.image.search', 'request_id': request_id,
            'image': {'mime': mime, 'base64': base64.b64encode(data).decode()}}))
        presentations = {}
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), 60))
            if event.get('request_id') != request_id:
                continue
            if event.get('type') == 'history.updated':
                presentations = event.get('presentations', {})
            if event.get('type') == 'knowledge.image.error':
                raise ValueError('Image search returned an error')
            if event.get('type') == 'knowledge.image.result':
                break
    products = [product for value in presentations.values()
                if value.get('type') == 'knowledge_product_carousel' for product in value['products']]
    actual = [product['source_label'] for product in products]
    originals_valid = True
    for product in products:
        url = urljoin(base + '/', product['image_url'])
        if urlsplit(url).netloc != urlsplit(base).netloc:
            raise ValueError('Unexpected image origin')
        image = await client.get(url)
        originals_valid &= image.status_code == 200 and hashlib.sha256(image.content).hexdigest() == product['asset_id']
    expected_status = 'matched' if case['expected_sources'] else 'no_match'
    return {'case': case['name'], 'expected': case['expected_sources'], 'actual': actual,
            'status': event.get('status'), 'originals_valid': originals_valid,
            'passed': actual == case['expected_sources'] and event.get('status') == expected_status and originals_valid,
            'seconds': round(time.monotonic() - started, 3)}


async def run(args):
    base = args.base_url.rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use an HTTP(S) base URL without credentials')
    manifest = Path(args.cases).resolve()
    cases = json.loads(manifest.read_text())
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError('Provide 1 to 100 cases')
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get('name'), str)
                or not isinstance(case.get('image'), str) or not isinstance(case.get('expected_sources'), list)
                or not all(isinstance(value, str) for value in case['expected_sources'])):
            raise ValueError('Invalid image case manifest')
    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(base + '/api/public/widget-config/' + args.widget_slug)
        response.raise_for_status()
        key = response.json()['apiKey']
        for case in cases:
            try:
                result = await check_case(client, base, key, case, manifest.parent, args.origin or f'{parsed.scheme}://{parsed.netloc}')
            except Exception as error:
                result = {'case': case['name'], 'passed': False, 'error_type': type(error).__name__}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if args.output:
                Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return all(result['passed'] for result in results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:18000')
    parser.add_argument('--widget-slug', required=True)
    parser.add_argument('--cases', required=True)
    parser.add_argument('--origin', help='Allowed browser Origin, if different from the API base')
    parser.add_argument('--output')
    arguments = parser.parse_args()
    try:
        success = asyncio.run(run(arguments))
    except Exception as error:
        print(json.dumps({'passed': False, 'error_type': type(error).__name__}))
        success = False
    raise SystemExit(0 if success else 1)
