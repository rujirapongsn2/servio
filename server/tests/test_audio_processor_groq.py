import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from audio_processor import groq


@pytest.fixture(autouse=True)
def groq_settings(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'secret-api-key')
    monkeypatch.delenv('KNOWLEDGE_AUDIO_GROQ_MODEL', raising=False)
    monkeypatch.delenv('KNOWLEDGE_AUDIO_GROQ_BASE_URL', raising=False)


def install_transport(monkeypatch, respond):
    client = httpx.AsyncClient
    def configured(**kwargs):
        assert kwargs['follow_redirects'] is False
        assert kwargs['trust_env'] is False
        return client(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', configured)


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / 'normalized.wav'
    path.write_bytes(b'fake normalized WAV')
    return path


@pytest.mark.parametrize('status,detail', [(401, 'authentication'), (429, 'rate limit'), (500, 'transcription failed'), (307, 'transcription failed')])
def test_remote_errors_are_safe_and_never_redirect(monkeypatch, audio, caplog, status, detail):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={'location': 'https://untrusted.example/secret-api-key'}, text='private transcript secret-api-key')
    install_transport(monkeypatch, respond)
    with pytest.raises(ValueError, match=detail) as error:
        groq.transcribe(audio, 1000)
    assert len(calls) == 1
    assert 'secret-api-key' not in str(error.value) + caplog.text
    assert 'private transcript' not in str(error.value) + caplog.text


@pytest.mark.parametrize('exception,detail', [(httpx.ReadTimeout, 'transcription timed out'), (httpx.ConnectError, 'request failed')])
def test_network_failures_are_safe(monkeypatch, audio, caplog, exception, detail):
    def respond(request):
        raise exception('private transcript secret-api-key', request=request)
    install_transport(monkeypatch, respond)
    with pytest.raises(ValueError, match=detail) as error:
        groq.transcribe(audio, 1000)
    assert 'secret-api-key' not in str(error.value) + caplog.text
    assert 'private transcript' not in str(error.value) + caplog.text


@pytest.mark.parametrize('payload', [
    b'not json private transcript', b'\xff', b'[]', b'{}',
    json.dumps({'segments': None}).encode(),
    json.dumps({'segments': [], 'text': 'private transcript'}).encode(),
    json.dumps({'segments': [], 'text': None}).encode(),
    json.dumps({'segments': [{'start': True, 'end': 1, 'text': 'secret-api-key'}]}).encode(),
    json.dumps({'segments': [{'start': 0, 'end': float('nan'), 'text': 'secret-api-key'}]}).encode(),
    json.dumps({'segments': [{'start': -1, 'end': 1, 'text': 'secret-api-key'}]}).encode(),
    json.dumps({'segments': [{'start': 0, 'end': 0, 'text': 'secret-api-key'}]}).encode(),
    json.dumps({'segments': [{'start': 0, 'end': 200, 'text': 'secret-api-key'}]}).encode(),
    json.dumps({'segments': [{'start': 0, 'end': 1, 'text': None}]}).encode(),
    json.dumps({'segments': [{'start': 0, 'end': 1, 'text': 'x' * 20001}]}).encode(),
    json.dumps({'segments': [], 'duration': float('inf')}).encode(),
    json.dumps({'segments': [], 'duration': '1'}).encode(),
    json.dumps({'segments': [], 'duration': 0}).encode(),
    json.dumps({'segments': [], 'duration': 100}).encode(),
    json.dumps({'segments': [None] * 10001}).encode(),
])
def test_malformed_transcripts_fail_closed(monkeypatch, audio, caplog, payload):
    install_transport(monkeypatch, lambda request: httpx.Response(200, content=payload))
    with pytest.raises(ValueError, match='Invalid Groq transcript') as error:
        groq.transcribe(audio, 1000)
    assert 'secret-api-key' not in str(error.value) + caplog.text
    assert 'private transcript' not in str(error.value) + caplog.text


def test_oversized_stream_stops_before_reading_rest(monkeypatch, audio):
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'x' * groq.MAX_RESPONSE_BYTES
            yield b'x'
            pytest.fail('read response beyond cap')
    install_transport(monkeypatch, lambda request: httpx.Response(200, stream=Stream()))
    with pytest.raises(ValueError, match='exceeds limit'):
        groq.transcribe(audio, 1000)


def test_empty_speech_and_rounded_endpoint_are_valid(monkeypatch, audio):
    responses = iter([{'segments': [], 'duration': 1}, {'segments': [{'start': 0, 'end': 1.01, 'text': ' Speech '}]}])
    install_transport(monkeypatch, lambda request: httpx.Response(200, json=next(responses)))
    assert groq.transcribe(audio, 1000) == []
    assert groq.transcribe(audio, 1000) == [(0, 1000, 'Speech')]


@pytest.mark.parametrize('base', [
    'https://untrusted.example/openai/v1', 'http://api.groq.com/openai/v1',
    'https://api.groq.com.evil.example/openai/v1',
    'https://secret-api-key@api.groq.com/openai/v1',
    'https://api.groq.com/openai/v1?secret-api-key=1',
    'https://api.groq.com/openai/v1#secret-api-key',
    'http://192.168.1.1:8095/openai/v1', 'http://localhost:invalid/openai/v1',
    'http://user:secret-api-key@127.0.0.1/openai/v1',
])
def test_endpoint_restrictions_fail_before_network(monkeypatch, audio, base):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_GROQ_BASE_URL', base)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: pytest.fail('invalid configuration contacted network'))
    with pytest.raises(ValueError, match='endpoint configuration') as error:
        groq.transcribe(audio, 1000)
    assert 'secret-api-key' not in str(error.value)


@pytest.mark.parametrize('base', ['http://127.0.0.1:18095/openai/v1', 'http://[::1]:18095/openai/v1', 'http://localhost:18095/openai/v1'])
def test_loopback_test_endpoint_is_allowed(monkeypatch, base):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_GROQ_BASE_URL', base)
    assert groq.configuration()[2] == base


@pytest.mark.parametrize('setting,value', [('GROQ_API_KEY', ''), ('GROQ_API_KEY', 'secret\napi-key'), ('KNOWLEDGE_AUDIO_GROQ_MODEL', 'secret invalid model')])
def test_credentials_and_model_are_validated_before_network(monkeypatch, audio, setting, value):
    monkeypatch.setenv(setting, value)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: pytest.fail('invalid configuration contacted network'))
    with pytest.raises(ValueError) as error:
        groq.transcribe(audio, 1000)
    assert 'secret' not in str(error.value)


def test_total_transcription_deadline_stops_trickled_response(monkeypatch, audio):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Content-Length', str(len(b'{"segments":[]}')))
            self.end_headers()
            try:
                for chunk in (b'{"segments":', b'[', b']}'):
                    time.sleep(.4)
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('KNOWLEDGE_AUDIO_GROQ_BASE_URL', f'http://127.0.0.1:{server.server_port}/openai/v1')
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS', '1')
    try:
        with pytest.raises(ValueError, match='transcription timed out'):
            groq.transcribe(audio, 1000)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
