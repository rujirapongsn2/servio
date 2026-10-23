import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest
from agents import RunContextWrapper

from app.custom_api import execute_custom_api_request, validate_custom_api_config


def configuration(**changes):
    return {
        'type': 'custom_api', 'endpoint': 'https://example.com/request',
        'method': 'POST', 'auth_token': '', 'timeout_seconds': 12,
        'request': {'version': 1, 'headers': [], 'query': [], 'body': {'kind': 'none'}},
        **changes,
    }


def invoke(config, query='hello'):
    from app.agent_config import create_custom_api_tool
    tool = create_custom_api_tool('custom_request', config)
    return asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), json.dumps({'query': query})))


@pytest.fixture
def echo_server():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            received.append({'method': self.command, 'path': self.path, 'headers': dict(self.headers), 'body': self.rfile.read(int(self.headers.get('Content-Length', '0')))})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(b'{"answer":"received"}')

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = handle_request

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/echo', received
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize('method', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])
def test_actual_http_method_headers_query_and_json_body(echo_server, method):
    endpoint, received = echo_server
    config = configuration(endpoint=endpoint + '?fixed=original', method=method, auth_token='secret')
    config['request'] = {
        'version': 1, 'headers': [{'name': 'X-Input', 'value': 'acceptance-only'}],
        'query': [{'name': 'tag', 'value': 'one'}, {'name': 'tag', 'value': '{{query}}'}],
        'body': {'kind': 'json', 'value': {'query': 'literal', 'nested': ['{{query}}', 3, False, None]}},
    }
    query = 'ไทย "quoted"'
    result = invoke(config, query)
    assert result == ('' if method == 'HEAD' else 'received')
    request = received[0]
    assert request['method'] == method
    assert parse_qsl(urlsplit(request['path']).query) == [('fixed', 'original'), ('tag', 'one'), ('tag', query)]
    assert request['headers']['Authorization'] == 'Bearer secret'
    assert request['headers']['X-Input'] == 'acceptance-only'
    assert request['headers']['Content-Type'] == 'application/json'
    assert json.loads(request['body']) == {'query': 'literal', 'nested': [query, 3, False, None]}


@pytest.mark.parametrize('body, expected, content_type', [
    ({'kind': 'json', 'value': None}, b'null', 'application/json'),
    ({'kind': 'text', 'value': 'raw {{query}}'}, 'raw ไทย "x"\nline'.encode(), None),
    ({'kind': 'form', 'fields': [{'name': 'q', 'value': '{{query}}'}, {'name': 'q', 'value': 'fixed'}]}, 'q=%E0%B9%84%E0%B8%97%E0%B8%A2+%22x%22%0Aline&q=fixed'.encode(), 'application/x-www-form-urlencoded'),
    ({'kind': 'none'}, b'', None),
])
def test_actual_body_encoding(echo_server, body, expected, content_type):
    endpoint, received = echo_server
    config = configuration(endpoint=endpoint, method='PATCH')
    config['request']['body'] = body
    response = execute_custom_api_request(config, 'ไทย "x"\nline')
    assert response.status_code == 200
    assert received[0]['body'] == expected
    assert received[0]['headers'].get('Content-Type') == content_type


def test_structural_substitution_preserves_json_types_and_literals(echo_server):
    endpoint, received = echo_server
    config = configuration(endpoint=endpoint)
    config['request']['body'] = {'kind': 'json', 'value': {'query': 'literal', 'message': 'literal too', 'value': '{{query}}', 'nested': {'key': '{{query}} suffix'}, 'number': 4, 'bool': True, 'null': None}}
    query = '"}, "injected":true\nไทย'
    assert invoke(config, query) == 'received'
    assert json.loads(received[0]['body']) == {'query': 'literal', 'message': 'literal too', 'value': query, 'nested': {'key': query + ' suffix'}, 'number': 4, 'bool': True, 'null': None}


@pytest.mark.parametrize('changes', [
    {'endpoint': 123}, {'endpoint': []}, {'endpoint': 'ftp://example.com'},
    {'endpoint': 'https://user:secret@example.com'}, {'endpoint': 'https://example.com/#secret'},
    {'method': 'TRACE'}, {'method': None}, {'timeout_seconds': 0},
    {'timeout_seconds': True}, {'timeout_seconds': float('nan')}, {'auth_token': 'secret\r\nInjected: true'},
    {'request': None}, {'request': {'version': 2}}, {'request': {'version': True}},
    {'request': {'version': 1, 'headers': [{'name': '', 'value': 'secret'}], 'query': [], 'body': {'kind': 'none'}}},
    {'request': {'version': 1, 'headers': [{'name': 'X-Key', 'value': 'secret'}, {'name': 'x-key', 'value': 'other'}], 'query': [], 'body': {'kind': 'none'}}},
    {'request': {'version': 1, 'headers': [{'name': 'X-Key', 'value': 'secret\n'}], 'query': [], 'body': {'kind': 'none'}}},
    {'request': {'version': 1, 'headers': [], 'query': [{'name': 'q', 'value': []}], 'body': {'kind': 'none'}}},
    {'request': {'version': 1, 'headers': [], 'query': [], 'body': {'kind': 'unknown'}}},
    {'request': {'version': 1, 'headers': [], 'query': [], 'body': {'kind': 'form', 'fields': [{'name': '', 'value': 'secret'}]}}},
    {'request': {'version': 1, 'headers': [], 'query': [], 'body': {'kind': 'json', 'value': float('nan')}}},
])
def test_invalid_configuration_is_rejected_without_outbound_or_secret(monkeypatch, changes):
    calls = []
    monkeypatch.setattr('requests.request', lambda *args, **kwargs: calls.append((args, kwargs)))
    config = configuration(**changes)
    with pytest.raises(ValueError) as error:
        validate_custom_api_config(config)
    assert 'secret' not in str(error.value)
    assert 'secret' not in invoke(config)
    assert calls == []


def test_credential_conflict_and_bound_header_injection_rejected(monkeypatch):
    calls = []
    monkeypatch.setattr('requests.request', lambda *args, **kwargs: calls.append((args, kwargs)))
    config = configuration(auth_token='secret')
    config['request']['headers'] = [{'name': 'authorization', 'value': 'Basic secret'}]
    with pytest.raises(ValueError):
        validate_custom_api_config(config)
    config['request']['headers'] = [{'name': 'X-Input', 'value': '{{query}}'}]
    assert 'secret' not in invoke(config, 'secret\r\nInjected: true')
    assert calls == []


def test_errors_redact_url_headers_and_body_and_refuse_redirect(monkeypatch):
    def failing(*args, **kwargs):
        raise RuntimeError('https://example.com/?key=secret Authorization: secret body=secret')
    monkeypatch.setattr('requests.request', failing)
    result = invoke(configuration(endpoint='https://example.com/?key=secret', auth_token='secret'))
    assert 'secret' not in result and 'Custom API request failed' in result
    called = []
    def redirect(*args, **kwargs):
        called.append(kwargs)
        return SimpleNamespace(status_code=302)
    monkeypatch.setattr('requests.request', redirect)
    result = invoke(configuration())
    assert 'Custom API request failed' in result
    assert called[0]['allow_redirects'] is False


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_legacy_http_execution_is_unchanged(monkeypatch, method):
    calls = []
    def respond(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'answer': 'legacy'})
    monkeypatch.setattr('requests.' + method.lower(), respond)
    monkeypatch.setattr('requests.request', lambda *args, **kwargs: pytest.fail('Legacy used modern executor'))
    config = {'endpoint': 'https://example.com', 'method': method, 'auth_token': 'old', 'timeout_seconds': 23, 'payload_template': {'message': 'old', 'fixed': 4}}
    assert invoke(config, 'new query') == 'legacy'
    assert calls == [(('https://example.com',), {'headers': {'Content-Type': 'application/json', 'Authorization': 'Bearer old'}, 'timeout': 23, **({'json': {'message': 'new query', 'fixed': 4}} if method == 'POST' else {'params': {'query': 'new query'}})})]
    assert config['payload_template']['message'] == 'old'


def test_modern_response_carousel_and_text_preserved(monkeypatch):
    from app.product_presentations import parse_product_carousel
    payload = {'type': 'product_carousel', 'version': 1, 'summary': 'Found', 'products': [{'id': 'sku-1', 'title': 'หัวเทียน'}]}
    monkeypatch.setattr('requests.request', lambda *args, **kwargs: SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: payload))
    assert parse_product_carousel(invoke(configuration())).products[0].id == 'sku-1'
    def not_json():
        raise ValueError()
    monkeypatch.setattr('requests.request', lambda *args, **kwargs: SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=not_json, text='Plain service response'))
    assert invoke(configuration()) == 'Plain service response'


def test_save_boundary_rejects_before_database_write(monkeypatch):
    from fastapi import HTTPException
    from app import db_config
    monkeypatch.setattr(db_config, "init_database", lambda: None)
    from app import admin_routes
    from app.models import CreateCustomToolRequest, UpdateCustomToolRequest
    monkeypatch.setattr(admin_routes, 'require_team_access', lambda *args: None)
    monkeypatch.setattr(admin_routes.database, 'create_custom_tool', lambda *args, **kwargs: pytest.fail('Invalid request saved'))
    monkeypatch.setattr(admin_routes.database, 'update_custom_tool', lambda *args, **kwargs: pytest.fail('Invalid request saved'))
    config = configuration(endpoint=123)
    for function, request_type, extra in [(admin_routes.create_tool, CreateCustomToolRequest, {}), (admin_routes.update_tool, UpdateCustomToolRequest, {'tool_id': 1})]:
        with pytest.raises(HTTPException) as error:
            asyncio.run(function(request=request_type(name='test', config=config), team_agent_id=None, current_user='admin', **extra))
        assert error.value.status_code == 400


def test_explicit_request_opts_into_generic_executor_and_legacy_softnix_keeps_dispatch(monkeypatch):
    from app import agent_config
    monkeypatch.setattr(agent_config, 'create_softnix_tool', lambda *args: 'softnix')
    monkeypatch.setattr(agent_config, 'create_custom_api_tool', lambda *args: 'generic')
    assert agent_config.get_tool_by_name('get_softnix_info', {'type': 'custom_api'}) == 'softnix'
    assert agent_config.get_tool_by_name('other', {'type': 'custom_api', 'api_type': 'softnix'}) == 'softnix'
    assert agent_config.get_tool_by_name('get_softnix_info', configuration(api_type='softnix')) == 'generic'


def test_modern_save_failure_does_not_return_database_parameters(monkeypatch):
    from app import db_config
    monkeypatch.setattr(db_config, 'init_database', lambda: None)
    from app import admin_routes
    from app.models import CreateCustomToolRequest
    from fastapi import HTTPException
    monkeypatch.setattr(admin_routes, 'require_team_access', lambda *args: None)
    def fail(*args, **kwargs):
        raise RuntimeError('SQL parameters: secret endpoint=https://example.com/?token=secret')
    monkeypatch.setattr(admin_routes.database, 'create_custom_tool', fail)
    with pytest.raises(HTTPException) as error:
        asyncio.run(admin_routes.create_tool(request=CreateCustomToolRequest(name='test', config=configuration()), team_agent_id=None, current_user='admin'))
    assert error.value.status_code == 500
    assert 'secret' not in error.value.detail
