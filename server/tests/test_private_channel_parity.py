"""Compare authenticated Private Chat HTTP and real Web Chat websocket entry points."""
import asyncio
import base64
from contextlib import asynccontextmanager
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from sqlalchemy import func
from test_workflow_creation import workspace, headers
from parity_fakes import FakeServices, api_config, VIN, MODEL_NAME
from app import agent_config, database, workflow_preview as preview
from app.orm_models import Agent, AgentTool, AgentHandoff, ApiKey, Conversation, LLMProvider, TeamAgentMember, Tool


@pytest.fixture
def parity(workspace, monkeypatch):
    client, get_db = workspace
    import app.db_config as db_config
    monkeypatch.setattr(db_config, 'get_db', get_db)
    fake = FakeServices()
    import requests, httpx
    original_send = httpx.AsyncClient.send
    async def send_only_fake(self, request, **kwargs):
        assert request.url.host == 'fake-model.invalid' and isinstance(self._transport, httpx.MockTransport), 'External network forbidden'
        return await original_send(self, request, **kwargs)
    monkeypatch.setattr(httpx.AsyncClient, 'send', send_only_fake)
    original_request = requests.Session.request
    def request_only_loopback(self, method, url, **kwargs):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        assert parsed.hostname == '127.0.0.1' and parsed.port == fake.server.server_port, 'External API forbidden'
        return original_request(self, method, url, **kwargs)
    monkeypatch.setattr(requests.Session, 'request', request_only_loopback)
    monkeypatch.setattr(agent_config, 'AsyncOpenAI', fake.client)
    monkeypatch.delenv('COORDINATOR_MODEL', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-global-key')
    monkeypatch.setenv('OPENAI_BASE_URL', 'http://fake-model.invalid/v1')
    # Import the real public entry point without loading .env or initializing a database.
    import app.environment as environment
    monkeypatch.setattr(environment, 'load_environment', lambda *args: False)
    import app.log_setup as log_setup
    monkeypatch.setattr(log_setup, 'configure_logging', lambda: None)
    from agents import set_tracing_disabled
    set_tracing_disabled(True)
    with patch('app.db_config.init_database'):
        spec = importlib.util.spec_from_file_location('servio_parity_entry', Path(__file__).parents[1]/'server.py')
        entry = importlib.util.module_from_spec(spec); spec.loader.exec_module(entry)
    async def no_intent(*args, **kwargs): pass
    monkeypatch.setattr(entry.intent_service, 'analyze_and_update', no_intent)
    import app.knowledge_image_search as images
    import app.local_image_rag as image_store
    import app.okf_service as okf
    monkeypatch.setattr(images, 'get_db', get_db)
    monkeypatch.setattr(image_store, 'get_db', get_db)
    monkeypatch.setattr(okf, 'get_db', get_db)
    monkeypatch.setattr(images, 'assigned_bundles', lambda *_: set())
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED', 'false')
    # Websocket route is the actual endpoint, not a helper replacement.
    client.app.router.routes.extend(route for route in entry.app.routes if getattr(route, 'path', None) == '/ws')
    with get_db() as db:
        provider=db.get(LLMProvider,1);provider.base_url='http://fake-model.invalid/v1';provider.api_key='fake-model-secret'
        agent=db.get(Agent,1);agent.model='fake-model';agent.llm_provider_id=1;agent.instructions='Route to Parts'
        db.add(Agent(id=3,name='Parts',instructions='Look up exact identifiers using the assigned service',model='fake-model',llm_provider_id=1));db.flush()
        db.add(TeamAgentMember(team_agent_id=1,agent_id=3));db.add(AgentHandoff(from_agent_id=1,to_agent_id=3))
        tool=db.get(Tool,2);tool.config=api_config(fake.endpoint);tool.name='VehicleLookup'
        db.add(AgentTool(agent_id=3,tool_id=2))
    preview._sessions.clear()
    try:
        yield client, get_db, fake, entry
    finally:
        for session in preview._sessions.values():session.media_directory.cleanup()
        preview._sessions.clear();fake.close()


def private_start(client):
    response=client.post('/api/admin/team-agents/1/workflow/previews',headers=headers(),json={'confirm_real_tools':True})
    assert response.status_code==200,response.text
    return response.json()['id']


def private_send(client, sid, message, **extra):
    response=client.post(f'/api/admin/team-agents/1/workflow/previews/{sid}/messages',headers=headers(),json={'message':message,**extra})
    assert response.status_code==200,response.text
    return response.json()


def channel_key(get_db):
    with get_db() as db:db.add(ApiKey(name='Fake Channel',key='fake-channel-key',team_agent_id=1,allowed_domains=['*']))


def channel_send(ws, message, **extra):
    ws.send_json({'type':'chat.input','message':message,**extra})
    for _ in range(200):
        result=ws.receive_json()
        if result.get('reason')=='response.done':return result
        assert result.get('type')!='error',result
    pytest.fail('No terminal response')


def test_real_entry_points_epc_schema_arguments_routing_history_and_followup(parity):
    client,get_db,fake,_=parity
    sid=private_start(client)
    with get_db() as db:assert db.query(ApiKey).count()==0  # Private Chat needs no Channel.
    greetings=private_send(client,sid,'hello')
    assert 'Hello' in greetings['response'] and not fake.requests
    clarify=private_send(client,sid,'help')
    assert 'provide' in clarify['response'] and not fake.requests
    answer=private_send(client,sid,VIN+' คือรถรุ่นอะไร')
    assert MODEL_NAME in answer['response']
    assert fake.requests[-1]['query']=={'vin':[VIN]}
    followup=private_send(client,sid,'which market?')
    assert 'ASIA' in followup['response'] and len(fake.requests)==1
    assert 'Hello' not in json.dumps(followup['a2ui'])
    assert MODEL_NAME not in json.dumps(followup['a2ui'])
    private_calls=deepcopy(fake.model_requests)
    with get_db() as db:assert db.query(Conversation).count()==0
    channel_key(get_db);fake.model_requests.clear()
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        assert ws.receive_json()['type']=='session.config'
        for question in ('hello','help',VIN+' คือรถรุ่นอะไร','which market?'):
            channel=channel_send(ws,question)
        assert any('ASIA' in json.dumps(item) for item in channel['inputs'])
    assert len(fake.requests)==2 and fake.requests[0]==fake.requests[1]
    # Compare actual OpenAI-compatible requests, including schemas/settings/context.
    def normalized(body):
        value=deepcopy(body);value.pop('stream',None);value.pop('stream_options',None)
        for message in value['messages']:
            if message.get('role')=='system':
                import re
                message['content']=re.sub(r'Current server datetime \(ISO-8601\): .*', 'Current server datetime (ISO-8601): <clock>', message['content'])
        return value
    assert [normalized(body) for body in private_calls]==[normalized(body) for body in fake.model_requests]
    for requests in (private_calls,fake.model_requests):
        actual_tool_args=[json.loads(call['function']['arguments']) for body in requests for item in body['messages'] for call in item.get('tool_calls',[]) if call['function']['name']=='VehicleLookup']
        assert {'vin':VIN} in actual_tool_args
        assert 'fake-api-secret' not in json.dumps(requests)
        assert any(item.get('role')=='tool' and MODEL_NAME in item.get('content','') for body in requests for item in body['messages'])


@pytest.mark.parametrize('arguments,expected,outbound', [({'vin':'NOT-A-VALID-ID'},'invalid_input',False),({'vin':'MR053BK4007006296'},'not_found',True)])
def test_http_200_business_outcomes_and_invalid_input_match(parity,arguments,expected,outbound):
    client,get_db,fake,_=parity;fake.force_arguments=arguments
    sid=private_start(client)
    private=private_send(client,sid,VIN+' คือรถรุ่นอะไร')
    assert expected in private['response'] and MODEL_NAME not in private['response']
    assert bool(fake.requests)==outbound
    channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();channel=channel_send(ws,VIN+' คือรถรุ่นอะไร')
    assert expected in json.dumps(channel['inputs'])
    assert len(fake.requests)==(2 if outbound else 0)


def test_failure_keeps_history_and_session_and_greetings_do_not_repeat_operation(parity):
    client,get_db,fake,_=parity
    sid=private_start(client);fake.fail_once=True
    result=private_send(client,sid,VIN+' คือรถรุ่นอะไร')
    assert 'tool_execution_error' in result['response']
    assert result['tool_calls'][0]['status']=='failed'
    private_send(client,sid,'hello');assert len(fake.requests)==1
    channel_key(get_db);fake.fail_once=True
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();channel=channel_send(ws,VIN+' คือรถรุ่นอะไร')
        assert 'tool_execution_error' in json.dumps(channel['inputs'])
        channel_send(ws,'hello')
    assert len(fake.requests)==2


def test_image_and_document_model_inputs_use_shared_adapter(parity):
    client,get_db,fake,_=parity
    image=io.BytesIO();Image.new('RGB',(4,4),'red').save(image,format='PNG')
    attachments=[{'kind':'image','name':'sample.png','mime':'image/png','base64':base64.b64encode(image.getvalue()).decode()},
                 {'kind':'file','name':'note.txt','mime':'text/plain','base64':base64.b64encode(b'Catalog note 42').decode()}]
    sid=private_start(client)
    result=private_send(client,sid,'Analyze attachment',attachments=attachments)
    assert 'image' in result['response']
    private_body=deepcopy(fake.model_requests[-1]);fake.model_requests.clear();channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();channel_send(ws,'Analyze attachment',attachments=attachments)
    def user(body):return [item['content'] for item in body['messages'] if item['role']=='user']
    assert user(private_body)==user(fake.model_requests[-1])
    assert 'Catalog note 42' in json.dumps(user(private_body))
    assert 'image_url' in json.dumps(user(private_body))


def test_legacy_query_reproduces_http200_2004_without_silently_rewriting_other_apis(parity):
    client,get_db,fake,_=parity
    with get_db() as db:db.get(Tool,2).config=api_config(fake.endpoint,structured=False)
    sid=private_start(client)
    question=VIN+' คือรถรุ่นอะไร'
    result=private_send(client,sid,question)
    assert 'invalid_input' in result['response'] and MODEL_NAME not in result['response']
    channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();channel=channel_send(ws,question)
    assert 'invalid_input' in json.dumps(channel['inputs'])
    assert fake.requests==[{'method':'GET','query':{'vin':[question]},'authorization':'Bearer fake-api-secret'}]*2


@pytest.mark.parametrize('error',[False,True])
def test_mcp_schema_remote_arguments_and_result_or_error_are_equal(parity,monkeypatch,error):
    from parity_fakes import install_mcp
    client,get_db,fake,_=parity;observed=[]
    install_mcp(monkeypatch,observed,error)
    monkeypatch.delenv('DISABLE_MCP',raising=False);monkeypatch.delenv('AGENTS_SAFE_MODE_DISABLE_EXTERNAL',raising=False)
    with get_db() as db:
        tool=db.get(Tool,2);tool.name='VehicleMCP';tool.type='mcp_streamable_http';tool.config={
            'type':'mcp_streamable_http','endpoint':'http://fake-mcp.invalid/mcp','auth_token':'fake-mcp-secret','tools':['lookup']}
    sid=private_start(client);result=private_send(client,sid,VIN+' คือรถรุ่นอะไร')
    assert ('tool_execution_error' if error else MODEL_NAME) in result['response']
    assert 'fake-mcp-secret' not in json.dumps(result)
    first=deepcopy(observed);channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();channel=channel_send(ws,VIN+' คือรถรุ่นอะไร')
        channel_send(ws,'hello')
    assert ('tool_execution_error' if error else MODEL_NAME) in json.dumps(channel['inputs'])
    assert observed[len(first):]==first
    assert first[1]=={'name':'lookup','arguments':{'vin':VIN}}
    assert 'fake-mcp-secret' not in json.dumps(fake.model_requests)


def test_audio_stt_tts_and_private_media_authorization_match_voice_channel(parity,monkeypatch):
    import wave
    from parity_fakes import FakeVoiceProvider
    from app import voice_config
    from fastapi.testclient import TestClient
    client,get_db,fake,_=parity;voice=FakeVoiceProvider()
    monkeypatch.setattr(voice_config,'voice_model_provider',lambda:voice)
    pcm=b'\x01\x00'*2400;out=io.BytesIO()
    with wave.open(out,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(pcm)
    attachment={'kind':'audio','name':'question.wav','mime':'audio/wav','base64':base64.b64encode(out.getvalue()).decode()}
    sid=private_start(client);response=private_send(client,sid,'',attachments=[attachment],speak=True)
    assert response['audio_url'].startswith('/api/admin/private-chat-media/')
    assert client.get(response['audio_url']).status_code==200
    assert client.get(response['audio_url'],headers=headers('other')).status_code==404
    with TestClient(client.app) as stranger:assert stranger.get(response['audio_url']).status_code==404
    channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();ws.send_json({'type':'input_audio_buffer.append','delta':base64.b64encode(pcm).decode()})
        ws.send_json({'type':'input_audio_buffer.commit'})
        received_audio=False
        for _ in range(200):
            event=ws.receive_json()
            received_audio |= event.get('type')=='response.audio.delta'
            if event.get('type')=='audio.done':break
        assert received_audio
    assert len(voice.stt_calls)==2 and voice.stt_calls[0]==voice.stt_calls[1]
    assert voice.tts_calls[0]['voice']==voice.tts_calls[-1]['voice']
    assert ''.join(call['text'] for call in voice.tts_calls[1:]).strip()==voice.tts_calls[0]['text']
    assert client.delete(f'/api/admin/team-agents/1/workflow/previews/{sid}',headers=headers()).status_code==200
    assert client.get(response['audio_url']).status_code==404


def test_video_uses_full_channel_processor_and_signed_evidence_outputs(parity,monkeypatch,tmp_path):
    import time
    from parity_fakes import processed_video
    from app import knowledge_video as video, video_attachments as clips
    client,get_db,fake,_=parity;calls=[]
    def process(path,**kwargs):
        calls.append(kwargs)
        assert not kwargs.get('preview',False)
        return processed_video(path.read_bytes())
    monkeypatch.setattr(video,'process_video',process);monkeypatch.setattr(video,'readiness',lambda:{'status':'ready'})
    monkeypatch.setenv('LOCAL_KNOWLEDGE_VIDEO_ENABLED','true')
    monkeypatch.setenv('VIDEO_ATTACHMENT_STORAGE_DIR',str(tmp_path/'clips'))
    monkeypatch.setattr(clips,'get_db',get_db)
    client.app.include_router(clips.router)
    sid=private_start(client)
    data=b'fake-video-source'
    response=private_send(client,sid,'Inspect video',attachments=[{'kind':'video','name':'clip.mp4','mime':'video/mp4','base64':base64.b64encode(data).decode()}])
    private_card=response['presentations']['uploaded_video']['videos'][0]
    assert client.get(private_card['poster_url']).status_code==200
    assert private_card['time_basis']=='frame_order' and private_card['duration_ms'] is None
    channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        config=ws.receive_json();grant=config['video_upload_token'];assert grant
        upload=client.post('/api/video-attachments',headers={'Authorization':'Bearer '+grant},files={'file':('clip.mp4',data,'video/mp4')})
        assert upload.status_code==202,upload.text
        assert clips.process_next()
        identity=upload.json()['attachment_id']
        status=client.get('/api/video-attachments/'+identity,headers={'Authorization':'Bearer '+grant}).json()
        assert status['status']=='ready',status
        card=status['presentation']['videos'][0]
        for field in ('asset_id','time_basis','duration_ms','complete','warnings','events'):
            assert card[field]==private_card[field]
        from uuid import uuid4
        ws.send_json({'type':'knowledge.video.inquire','request_id':str(uuid4()),'attachment_id':identity,'query':'Inspect video'})
        for _ in range(200):
            event=ws.receive_json()
            if event.get('reason')=='response.done':break
        assert any(value['type']=='knowledge_video' for value in event['presentations'].values())
    assert len(calls)==2


def test_citations_tables_and_products_use_the_channel_presenter(parity,monkeypatch):
    from agents import function_tool
    from app.a2ui_answers import read_result, Source
    client,get_db,fake,_=parity
    original=agent_config.get_tool_by_name
    def factory(name,config,*args,**kwargs):
        if name=='KnowledgeLookup':
            @function_tool(name_override=name)
            def knowledge(query:str)->str:
                return read_result('Manual answer',{'model':'Example'},sources=[Source(title='Manual',excerpt='Verified excerpt')])
            knowledge._servio_read_results=True
            return knowledge
        if name=='CatalogLookup':
            @function_tool(name_override=name)
            def catalog(query:str)->str:
                return json.dumps({'type':'product_carousel','version':1,'summary':'Catalog products','products':[{'id':'product-a','title':'Product A','part_number':'MODEL-A'}]})
            return catalog
        return original(name,config,*args,**kwargs)
    monkeypatch.setattr(agent_config,'get_tool_by_name',factory)
    with get_db() as db:
        for ident,name in ((4,'KnowledgeLookup'),(5,'CatalogLookup')):
            db.add(Tool(id=ident,name=name,type='custom_api',owner_team_agent_id=1,config={'type':'custom_api'}));db.flush();db.add(AgentTool(agent_id=3,tool_id=ident))
    sid=private_start(client);answer=private_send(client,sid,'knowledge')
    assert 'Verified excerpt' in json.dumps(answer['a2ui'])
    product=private_send(client,sid,'products')
    assert product['presentations'] and 'MODEL-A' in json.dumps(product['presentations'])
    assert 'Verified excerpt' not in json.dumps(product['a2ui'])
    channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();ws.send_json({'type':'a2ui.capabilities','a2uiClientCapabilities':{'supportedCatalogIds':['https://servio.ai/a2ui/catalogs/answers/v1']}})
        channel=channel_send(ws,'knowledge')
        assert 'Verified excerpt' in json.dumps(channel['a2ui'])
        channel=channel_send(ws,'products')
        assert 'MODEL-A' in json.dumps(channel['presentations'])


def test_messaging_handler_retains_tool_evidence_and_followup(parity, monkeypatch):
    from app.messaging import handler
    client, get_db, fake, _ = parity
    monkeypatch.setattr(handler, '_conversations', {})
    async def scenario():
        first = await handler.handle_message('fake', 'customer', VIN+' คือรถรุ่นอะไร', team_agent_id=1)
        second = await handler.handle_message('fake', 'customer', 'which market?', team_agent_id=1)
        assert MODEL_NAME in first and 'earlier tool result' in second
        history = handler.get_or_create_conversation('fake', 'customer', 1)
        assert any(item.get('type') == 'function_call_output' for item in history)
        assert not handler.get_or_create_conversation('fake', 'other-customer', 1)
    asyncio.run(scenario())
    assert len(fake.requests) == 1 and fake.requests[0]['query'] == {'vin': [VIN]}


def test_uncertain_write_is_not_retried_with_changed_arguments():
    from agents import Agent as RuntimeAgent, function_tool
    from app.tool_execution import protect_tools
    from app.agent_execution import execution_scope
    calls = []
    @function_tool
    async def write_record(value: str) -> str:
        calls.append(value)
        raise RuntimeError('Remote write may have committed')
    write_record._servio_may_write = True
    agent = RuntimeAgent(name='Writer', tools=[write_record])
    protect_tools([agent], [])
    async def scenario():
        with execution_scope(agent) as events:
            first = await write_record.on_invoke_tool(None, '{"value":"one"}')
            second = await write_record.on_invoke_tool(None, '{"value":"two"}')
            assert first == second and 'automatic_retry_allowed' in first
            assert [entry['status'] for entry in events] == ['failed', 'retry_blocked']
    asyncio.run(scenario())
    assert calls == ['one']


def test_draft_image_search_uses_authorized_bundles_and_shared_channel_search(parity, monkeypatch, tmp_path):
    import app.knowledge_image_search as search
    import app.utils as utils
    from app.orm_models import OKFBundle
    client, get_db, fake, _ = parity
    monkeypatch.setattr(search.images, 'enabled', lambda: True)
    # Fixture normally disables image-library search to isolate native model input.
    monkeypatch.setattr(search, 'assigned_bundles', lambda team: search.runtime_bundle_scope.get()(team) if search.runtime_bundle_scope.get() else {7})
    with get_db() as db:
        db.add(OKFBundle(id=7, name='Draft images', display_name='Draft images', storage_path=str(tmp_path), owner_team_agent_id=1, visibility='team', status='ready'))
        db.add(Tool(id=7, name='DraftImages', type='okf_knowledge_graph', owner_team_agent_id=1, config={'type':'okf_knowledge_graph','okf_bundle_id':7}))
    snapshot = client.get('/api/admin/team-agents/1/workflow', headers=headers()).json()
    member = next(agent for agent in snapshot['agents'] if agent['id'] == 3)
    fields = ('name','instructions','model','llm_provider_id','tool_ids','handoff_agent_ids')
    draft = {key: member[key] for key in fields}; draft['tool_ids'] = [*draft['tool_ids'],7]
    response = client.post('/api/admin/team-agents/1/workflow/previews', headers=headers(), json={'confirm_real_tools':True,'drafts':[{'agent_id':3,'draft':draft}]})
    assert response.status_code == 200, response.text
    sid = response.json()['id']; seen = []
    def image_search(team, request):
        seen.append((team, search.assigned_bundles(team), request.image_bytes(), request.query))
        if search.runtime_bundle_scope.get():
            assert search.assigned_bundles(2) == set()
        return search.SearchResult('no_match')
    monkeypatch.setattr(utils, 'search_image', image_search)
    png=io.BytesIO();Image.new('RGB',(8,8),'beige').save(png,format='PNG')
    image={'mime':'image/png','base64':base64.b64encode(png.getvalue()).decode()}
    answer=private_send(client,sid,'similar tile',image_search=True,attachments=[{'kind':'image','name':'tile.png',**image}])
    assert 'ไม่พบ' in answer['response'] and not fake.model_requests
    channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json();ws.send_json({'type':'knowledge.image.search','request_id':'image-test','image':image,'query':'similar tile'})
        for _ in range(100):
            event=ws.receive_json()
            if event.get('type')=='knowledge.image.complete':break
            if event.get('reason')=='image.search':break
            if event.get('type')=='history.updated' and 'ไม่พบ' in json.dumps(event,ensure_ascii=False):break
        else:pytest.fail('Missing image result')
    assert len(seen)==2 and seen[0]==seen[1]


def test_legacy_channel_text_budget_preserves_session(parity):
    client, get_db, fake, _ = parity
    channel_key(get_db)
    with client.websocket_connect('/ws?api_key=fake-channel-key') as ws:
        ws.receive_json()
        ws.send_json({'type':'history.update','inputs':[{'role':'user','content':'x'*32001}]})
        assert ws.receive_json()['type']=='error'
        assert not fake.model_requests
        result = channel_send(ws, 'hello')
        assert 'Hello' in json.dumps(result['inputs'])
