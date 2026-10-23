import base64
import io
import json
import shutil
import wave
import pytest
from fastapi.testclient import TestClient
from audio_processor import service


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
def test_required_vad_command_clamps_timestamps_and_empty_transcript(tmp_path,monkeypatch):
    for key in ['CLI','MODEL']:
        file=tmp_path/key;file.write_text('fake');monkeypatch.setenv('KNOWLEDGE_AUDIO_WHISPER_'+key,str(file))
    vad=tmp_path/'vad';vad.write_text('fake');monkeypatch.setenv('KNOWLEDGE_AUDIO_VAD_MODEL',str(vad));monkeypatch.setenv('KNOWLEDGE_AUDIO_ASR_REVISION','small-sha-silero-sha')
    original=service.run;calls=[]
    def run(argv,timeout=120):
        if argv[0]==str(tmp_path/'CLI'):
            calls.append(argv)
            prefix=argv[argv.index('-of')+1]
            open(prefix+'.json','w').write(json.dumps({'transcription':[{'offsets':{'from':0,'to':3000},'text':' Actual speech '}]}))
            return b''
        return original(argv,timeout)
    monkeypatch.setattr(service,'run',run)
    result=service.analyze(wav(),tmp_path,transcribe=True)
    assert result['audio']['segments'][0]['transcript']=='Actual speech'
    assert result['audio']['segments'][0]['end_ms']==1000
    assert '--vad' in calls[0] and '-vm' in calls[0] and '-ng' in calls[0] and calls[0][calls[0].index('-t')+1]=='2'


def test_busy_processor_rejects_without_reading_body():
    service._lane.acquire()
    try:
        response=TestClient(service.app).post('/extract',content=b'audio')
        assert response.status_code==429
    finally:service._lane.release()
