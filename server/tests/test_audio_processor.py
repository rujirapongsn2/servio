import base64
import io
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import shutil
import wave
import pytest
from fastapi.testclient import TestClient
from audio_processor import service


@pytest.fixture(autouse=True)
def isolated_processor_settings(monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'local')
    for name in ('GROQ_API_KEY', 'KNOWLEDGE_AUDIO_GROQ_MODEL', 'KNOWLEDGE_AUDIO_GROQ_BASE_URL',
                 'KNOWLEDGE_AUDIO_SEGMENT_SECONDS', 'KNOWLEDGE_AUDIO_OVERLAP_SECONDS',
                 'KNOWLEDGE_AUDIO_MAX_SECONDS'):
        monkeypatch.delenv(name, raising=False)


def wav(seconds=1):
    output=io.BytesIO()
    with wave.open(output,'wb') as handle:
        handle.setnchannels(1);handle.setsampwidth(2);handle.setframerate(16000);handle.writeframes(b'\0\0'*(16000*seconds))
    return output.getvalue()


@pytest.mark.parametrize('data',[b'',b'not audio',b'<html>renamed.mp3</html>',b'x'*(50*1024*1024+1)])
def test_invalid_renamed_or_oversize_rejected_before_subprocess(data,tmp_path,monkeypatch):
    monkeypatch.setattr(service,'run',lambda *a,**kw:pytest.fail('invalid upload invoked decoder'))
    with pytest.raises(ValueError):service.analyze(data,tmp_path)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local ffmpeg required')
def test_preview_and_normalize_are_asr_free_and_preserve_windows(tmp_path,monkeypatch):
    monkeypatch.delenv('KNOWLEDGE_AUDIO_WHISPER_CLI',raising=False)
    preview=service.analyze(wav(27),tmp_path)
    assert preview['audio']['duration_ms']==27000
    assert [(s['start_ms'],s['end_ms']) for s in preview['audio']['segments']]==[(0,20000),(18000,27000)]
    other=tmp_path/'normalized';other.mkdir()
    normalized=service.analyze(wav(27),other,normalize=True)
    assert len(normalized['wav_segments'])==2
    for encoded in normalized['wav_segments']:
        with wave.open(io.BytesIO(base64.b64decode(encoded))) as handle:
            assert (handle.getnchannels(),handle.getframerate(),handle.getsampwidth())==(1,16000,2)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local ffmpeg required')
def test_duration_limit_and_asr_configuration_are_required(tmp_path,monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_MAX_SECONDS','1')
    with pytest.raises(ValueError,match='duration'):service.analyze(wav(2),tmp_path)
    monkeypatch.delenv('KNOWLEDGE_AUDIO_WHISPER_CLI',raising=False)
    with pytest.raises(KeyError):service.analyze(wav(),tmp_path,transcribe=True)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local ffmpeg required')
@pytest.mark.parametrize('gpu',[None,'false','true'])
def test_required_vad_command_clamps_timestamps_and_empty_transcript(tmp_path,monkeypatch,gpu):
    if gpu is None:monkeypatch.delenv('KNOWLEDGE_AUDIO_USE_GPU',raising=False)
    else:monkeypatch.setenv('KNOWLEDGE_AUDIO_USE_GPU',gpu)
    for key in ['CLI','MODEL']:
        file=tmp_path/key;file.write_text('fake');monkeypatch.setenv('KNOWLEDGE_AUDIO_WHISPER_'+key,str(file))
    vad=tmp_path/'vad';vad.write_text('fake');monkeypatch.setenv('KNOWLEDGE_AUDIO_VAD_MODEL',str(vad));monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_REVISION','small-sha-silero-sha')
    original=service.run;calls=[]
    def run(argv,timeout=120,**kwargs):
        if argv[0]==str(tmp_path/'CLI'):
            calls.append(argv)
            prefix=argv[argv.index('-of')+1]
            open(prefix+'.json','w').write(json.dumps({'transcription':[{'offsets':{'from':0,'to':3000},'text':' Actual speech '}]}))
            return b''
        return original(argv,timeout,**kwargs)
    monkeypatch.setattr(service,'run',run)
    result=service.analyze(wav(),tmp_path,transcribe=True)
    assert result['audio']['segments'][0]['transcript']=='Actual speech'
    assert result['audio']['segments'][0]['end_ms']==1000
    assert '--vad' in calls[0] and '-vm' in calls[0]
    assert ('-ng' in calls[0]) == (gpu != 'true')
    assert calls[0][calls[0].index('-t')+1]=='2'


def test_busy_processor_rejects_without_reading_body():
    service._lane.acquire()
    try:
        response=TestClient(service.app).post('/extract',content=b'audio')
        assert response.status_code==429
    finally:service._lane.release()


@pytest.mark.parametrize('stage',['probe','decode','transcription'])
def test_subprocess_timeout_identifies_stage_without_output(monkeypatch,stage,caplog):
    import subprocess
    def fail(*args,**kwargs):
        raise subprocess.TimeoutExpired(args[0],kwargs['timeout'],output=b'private transcript',stderr=b'secret path')
    monkeypatch.setattr(service.subprocess,'run',fail)
    with pytest.raises(ValueError,match=stage+' timed out') as error:
        service.run(['fake'],timeout=5,stage=stage)
    assert 'private transcript' not in str(error.value)+caplog.text
    assert 'secret path' not in str(error.value)+caplog.text
    assert 'elapsed_seconds=' in caplog.text


def test_unexpected_processor_errors_do_not_leak_to_client(monkeypatch):
    def fail(*args):raise KeyError('secret config or transcript')
    monkeypatch.setattr(service,'analyze',fail)
    response=TestClient(service.app).post('/extract',content=b'audio')
    assert response.status_code==422
    assert 'secret config' not in response.text


@pytest.mark.parametrize('configured',[None,'1200','1','99999'])
def test_http_budget_covers_independently_configured_max_asr(monkeypatch,configured):
    from app import knowledge_audio
    import httpx
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED','true')
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS','1')
    if configured is None:monkeypatch.delenv('KNOWLEDGE_AUDIO_TIMEOUT_SECONDS',raising=False)
    else:monkeypatch.setenv('KNOWLEDGE_AUDIO_TIMEOUT_SECONDS',configured)
    budgets=[]
    def post(*args,**kwargs):
        budgets.append(kwargs['timeout'])
        raise httpx.ReadTimeout('secret URL or transcript')
    monkeypatch.setattr(knowledge_audio.httpx,'post',post)
    with pytest.raises(ValueError,match='request timed out; previous source retained'):
        knowledge_audio.process_audio(b'audio')
    assert 1800+60+120+120+60 < budgets[0] <= 3600


@pytest.mark.parametrize('configured,expected',[(None,1200),('1',1),('1800',1800),('99999',1800),('0',1)])
def test_asr_budget_is_bounded(monkeypatch,configured,expected):
    from app.knowledge_audio import asr_timeout
    if configured is None:monkeypatch.delenv('KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS',raising=False)
    else:monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS',configured)
    assert asr_timeout()==expected


@pytest.mark.parametrize('setting',['KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS','KNOWLEDGE_AUDIO_TIMEOUT_SECONDS'])
@pytest.mark.parametrize('value',['NaN','inf','secret invalid value'])
def test_invalid_timeout_config_is_safe(monkeypatch,setting,value):
    from app.knowledge_audio import timeout_budget
    monkeypatch.setenv(setting,value)
    with pytest.raises(ValueError,match='Invalid local audio timeout configuration') as error:
        timeout_budget(setting,1200,1,1800)
    assert value not in str(error.value)


@pytest.mark.parametrize('detail,expected',[
    ('Local audio transcription timed out; previous source retained','transcription timed out'),
    ('private subprocess output or secret','Local audio processing failed'),
])
def test_backend_forwards_only_safe_timeout_detail(monkeypatch,detail,expected):
    from app import knowledge_audio
    import httpx
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED','true')
    monkeypatch.setattr(knowledge_audio.httpx,'post',lambda *a,**kw:httpx.Response(422,json={'detail':detail}))
    with pytest.raises(ValueError,match=expected) as error:
        knowledge_audio.process_audio(b'audio')
    assert 'private subprocess' not in str(error.value)


def test_invalid_gpu_configuration_rejected(monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_USE_GPU','maybe')
    with pytest.raises(ValueError,match='Invalid local audio GPU configuration'):
        service.use_gpu()


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local ffmpeg required')
def test_groq_extract_projects_transcript_without_local_assets(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'groq')
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')
    monkeypatch.delenv('KNOWLEDGE_AUDIO_WHISPER_CLI', raising=False)
    requests = []
    client = httpx.AsyncClient
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'duration': 27, 'segments': [
            {'start': 1, 'end': 2, 'text': ' First '},
            {'start': 19, 'end': 21, 'text': 'Across windows'},
            {'start': 23, 'end': 26, 'text': 'Last'},
        ]})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    result = service.analyze(wav(27), tmp_path, transcribe=True)
    assert [row['transcript'] for row in result['audio']['segments']] == ['First Across windows', 'Across windows Last']
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == 'https://api.groq.com/openai/v1/audio/transcriptions'
    assert request.headers['authorization'] == 'Bearer test-key'
    body = request.content
    for value in [b'whisper-large-v3-turbo', b'verbose_json', b'timestamp_granularities[]', b'segment', b'audio/wav']:
        assert value in body
    start = body.index(b'RIFF')
    with wave.open(io.BytesIO(body[start:])) as audio:
        assert (audio.getnchannels(), audio.getframerate(), audio.getsampwidth(), audio.getnframes()) == (1, 16000, 2, 432000)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local ffmpeg required')
def test_groq_preview_normalize_need_no_credentials_or_remote(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'groq')
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: pytest.fail('preview/normalize contacted Groq'))
    result = service.analyze(wav(), tmp_path)
    other = tmp_path / 'normalize'; other.mkdir()
    assert service.analyze(wav(), other, normalize=True)['wav_segments']
    assert result['audio']['transcript_status'] == 'empty'


def test_groq_health_ignores_local_assets_and_gpu(monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'groq')
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')
    monkeypatch.setenv('KNOWLEDGE_AUDIO_USE_GPU', 'invalid-local-setting')
    monkeypatch.delenv('KNOWLEDGE_AUDIO_WHISPER_CLI', raising=False)
    monkeypatch.setattr(service.shutil, 'which', lambda binary: '/fake/' + binary)
    result = service.health()
    assert result['ready'] is True
    assert result['provider'] == 'groq'
    assert 'whisper_cli' not in result['dependencies']
    assert 'use_gpu' not in result
    monkeypatch.delenv('GROQ_API_KEY')
    assert service.health()['ready'] is False


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local ffmpeg required')
def test_default_local_fingerprint_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', raising=False)
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_REVISION', 'historical-revision')
    result = service.analyze(wav(), tmp_path)
    expected = hashlib.sha256(json.dumps(['pcm16-mono16k-v1', 20000, 2000, 'historical-revision', 'required-silero-vad-v1']).encode()).hexdigest()
    assert result['audio']['fingerprint'] == expected


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local ffmpeg required')
def test_groq_fingerprint_tracks_model_not_local_weights(tmp_path, monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'groq')
    initial = service.analyze(wav(), tmp_path)['audio']['fingerprint']
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_REVISION', 'different-local-weights')
    other = tmp_path / 'other'; other.mkdir()
    assert service.analyze(wav(), other)['audio']['fingerprint'] == initial
    monkeypatch.setenv('KNOWLEDGE_AUDIO_GROQ_MODEL', 'whisper-large-v3')
    third = tmp_path / 'third'; third.mkdir()
    assert service.analyze(wav(), third)['audio']['fingerprint'] != initial
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'local')
    fourth = tmp_path / 'fourth'; fourth.mkdir()
    assert service.analyze(wav(), fourth)['audio']['fingerprint'] != initial


def test_unknown_provider_health_fails_safely(monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_PROVIDER', 'private-invalid-value')
    result = service.health()
    assert result['ready'] is False
    assert 'private-invalid-value' not in json.dumps(result)


def test_processor_dotenv_load_is_scoped_and_preserves_exported_values(tmp_path):
    root = tmp_path / 'project'
    processor = root / 'server' / 'audio_processor'
    processor.mkdir(parents=True)
    module = processor / 'service.py'
    shutil.copyfile(service.__file__, module)
    (root / '.env').write_text('KNOWLEDGE_AUDIO_ASR_PROVIDER=groq\nGROQ_API_KEY=file-key\nDATABASE_URL=unrelated-database\nAUDIO_EMBEDDING_MODEL=unrelated-model\nLOCAL_KNOWLEDGE_AUDIO_ENABLED=true\n')
    environment = dict(os.environ, PYTHONPATH=str(Path(service.__file__).resolve().parents[1]), KNOWLEDGE_AUDIO_ASR_PROVIDER='local')
    for name in ('GROQ_API_KEY', 'DATABASE_URL', 'AUDIO_EMBEDDING_MODEL', 'LOCAL_KNOWLEDGE_AUDIO_ENABLED'):
        environment.pop(name, None)
    result = subprocess.run([sys.executable, '-c',
        'import json,os,runpy,sys; runpy.run_path(sys.argv[1]); print(json.dumps({key:os.getenv(key) for key in ["KNOWLEDGE_AUDIO_ASR_PROVIDER","GROQ_API_KEY","DATABASE_URL","AUDIO_EMBEDDING_MODEL","LOCAL_KNOWLEDGE_AUDIO_ENABLED"]}))',
        str(module)], capture_output=True, check=True, text=True, env=environment)
    assert json.loads(result.stdout) == {'KNOWLEDGE_AUDIO_ASR_PROVIDER': 'local', 'GROQ_API_KEY': 'file-key',
        'DATABASE_URL': None, 'AUDIO_EMBEDDING_MODEL': None, 'LOCAL_KNOWLEDGE_AUDIO_ENABLED': None}
