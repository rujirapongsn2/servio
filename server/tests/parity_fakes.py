"""Offline model protocol and EPC fixtures. Never imported by application code."""
import json
import re
import time
from urllib.parse import parse_qs, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
from openai import AsyncOpenAI

VIN = 'MR053BK4007006295'
MODEL_NAME = 'TOYOTA CAMRY/HYBRID (ASIA)'
VIN_PATTERN = r'^[A-HJ-NPR-Z0-9]{17}$'


def api_config(endpoint, structured=True):
    result = {'type': 'custom_api', 'endpoint': endpoint, 'method': 'GET', 'auth_token': 'fake-api-secret',
        'description': 'Look up a vehicle using its exact identifier. Ask for missing input.',
        'request': {'version': 1, 'headers': [], 'query': [{'name': 'vin', 'value': '{{args.vin}}' if structured else '{{query}}'}], 'body': {'kind': 'none'}},
        # These are the fake service's documented codes, not claims about the real EPC contract.
        'result_contract': {'status_path': 'error_code', 'success_values': [0], 'not_found_values': [4040], 'invalid_input_values': [2004]}}
    if structured:
        result['input_schema'] = {'type': 'object', 'properties': {'vin': {'type': 'string', 'pattern': VIN_PATTERN, 'description': 'Exact identifier only, excluding the question text'}}, 'required': ['vin'], 'additionalProperties': False}
    return result


class FakeServices:
    def __init__(self):
        self.requests = []
        self.model_requests = []
        self.force_arguments = None
        self.fail_once = False
        self.tool_result = None
        observed = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parameters = parse_qs(urlsplit(self.path).query)
                observed.requests.append({'method': self.command, 'query': parameters, 'authorization': self.headers.get('Authorization')})
                vin = parameters.get('vin', [''])[0]
                if observed.fail_once:
                    observed.fail_once = False
                    self.send_response(503); self.end_headers(); return
                payload = ({'error_code': 0, 'vehicle': MODEL_NAME} if vin == VIN else
                           {'error_code': 4040, 'message': 'not found'} if re.fullmatch(VIN_PATTERN, vin) else
                           {'error_code': 2004, 'message': 'invalid input'})
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(payload).encode())
            def log_message(self, *args): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f'http://127.0.0.1:{self.server.server_port}/epc'

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def client(self, **kwargs):
        return AsyncOpenAI(**kwargs, max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.model)))

    async def model(self, request):
        assert request.url.host == 'fake-model.invalid', 'No external model endpoint is allowed'
        if request.method == 'GET' and request.url.path.endswith('/models'):
            return httpx.Response(200, json={'object':'list','data':[{'id':'fake-model','object':'model','created':1,'owned_by':'dev-fixture'}]})
        body = json.loads(request.content)
        self.model_requests.append(body)
        messages = body['messages']
        system = '\n'.join(item.get('content') or '' for item in messages if item['role'] in ('system', 'developer'))
        tools = [item['function'] for item in body.get('tools', [])]
        user_index = max(i for i, item in enumerate(messages) if item['role'] == 'user')
        content = messages[user_index]['content']
        query = content if isinstance(content, str) else '\n'.join(item.get('text', '') for item in content)
        outputs = [item for item in messages[user_index+1:] if item['role'] == 'tool' and not item.get('tool_call_id', '').startswith('call_transfer_to_')]
        all_outputs = [item for item in messages if item['role'] == 'tool']
        function = arguments = None
        if 'You are the Coordinator Agent' in system:
            function = next(item['name'] for item in tools if item['name'].startswith('transfer_to_'))
            arguments = {}
        elif 'Route to Parts' in system:
            function = next(item['name'] for item in tools if item['name'].startswith('transfer_to_'))
            arguments = {}
        elif query.lower().strip() in ('hello', 'hi', 'สวัสดี'):
            answer = 'Hello. How can I help?'
        elif query.lower().strip() == 'help':
            answer = 'Please provide the vehicle identifier.'
        elif query.lower().strip() == 'which market?':
            answer = 'ASIA, from the earlier tool result.' if any(MODEL_NAME in item['content'] for item in all_outputs) else 'Please provide an identifier.'
        elif outputs and not any('transfer_to_' in item.get('content', '') for item in outputs):
            answer = outputs[-1]['content']
            try:
                decoded = json.loads(answer)
                if decoded.get('type') == 'servio_read_result': answer = decoded['response']
                elif decoded.get('type') == 'product_carousel': answer = 'Found catalog products'
            except (ValueError, AttributeError): pass
        elif query.lower().strip() in ('knowledge','manual'):
            function = 'KnowledgeLookup'; arguments = {'query': query}
        elif query.lower().strip() == 'products':
            function = 'CatalogLookup'; arguments = {'query': query}
        elif query.lower().startswith('inspect video'):
            answer = 'Observed sampled frames; clock time is unknown.'
        elif re.search(r'[A-HJ-NPR-Z0-9]{17}', query) or self.force_arguments is not None:
            function = next(item['name'] for item in tools if not item['name'].startswith('transfer_to_') and item['name'] != 'DateTimeTool')
            definition = next(item for item in tools if item['name'] == function)
            arguments = self.force_arguments
            if arguments is None:
                arguments = {'vin': re.search(r'[A-HJ-NPR-Z0-9]{17}', query).group()} if 'vin' in definition['parameters'].get('properties', {}) else {'query': json.dumps({'vin': re.search(r'[A-HJ-NPR-Z0-9]{17}', query).group()})} if function == 'VehicleMCP' else {'query': query}
        elif isinstance(content, list) and any(item.get('type') == 'image_url' for item in content):
            answer = 'Received the image for analysis.'
        else:
            answer = query or 'Ready'
        if function:
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_'+function, 'type': 'function', 'function': {'name': function, 'arguments': json.dumps(arguments)}}]}
        else:
            message = {'role': 'assistant', 'content': answer}
        common = {'id': 'chatcmpl-fake', 'created': 1, 'model': 'fake-model'}
        if body.get('stream'):
            delta = message.copy(); delta.pop('role', None)
            if 'tool_calls' in delta:
                delta['tool_calls'][0]['index'] = 0
            chunk = {**common, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}
            end = {**common, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls' if function else 'stop'}]}
            return httpx.Response(200, headers={'Content-Type': 'text/event-stream'}, content=('data: '+json.dumps(chunk)+'\n\ndata: '+json.dumps(end)+'\n\ndata: [DONE]\n\n').encode())
        return httpx.Response(200, json={**common, 'object': 'chat.completion', 'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if function else 'stop'}], 'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})


class FakeVoiceProvider:
    def __init__(self, transcript='hello'):
        self.transcript = transcript
        self.stt_calls, self.tts_calls = [], []
    def get_stt_model(self, name):
        owner = self
        class STT:
            async def transcribe(self, audio, settings, trace_include_sensitive_data, trace_include_sensitive_audio_data):
                owner.stt_calls.append({'model': name, 'rate': audio.frame_rate, 'channels': audio.channels,
                    'bytes': audio.to_audio_file()[1].getvalue(), 'language': settings.language, 'prompt': settings.prompt, 'temperature': settings.temperature})
                return owner.transcript
        return STT()
    def get_tts_model(self, name):
        owner = self
        class TTS:
            model_name = name
            async def run(self, text, settings):
                owner.tts_calls.append({'model':name,'text':text,'voice':settings.voice,'instructions':settings.instructions})
                yield b'\x00\x00' * 2400
        return TTS()


def processed_video(data):
    import hashlib, io
    from PIL import Image
    from app import knowledge_video as video
    out = io.BytesIO(); Image.new('RGB',(32,32),'tan').save(out,format='JPEG')
    frame = out.getvalue(); asset=hashlib.sha256(frame).hexdigest()
    evidence = video.VideoEvidence(asset_id=hashlib.sha256(data).hexdigest(), mime='video/mp4',
        time_basis='frame_order', duration_ms=None, complete=False, warnings=['Sampled frames'], processed_frames=2,
        fingerprint='c'*64, frames=[video.VideoFrame(frame_index=i,image_asset_id=asset,observations='Door visible') for i in (0,30)], events=[])
    return video.ProcessedVideo(evidence,data,{asset:frame})


def install_mcp(monkeypatch, observed, error=False):
    from contextlib import asynccontextmanager
    from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
    from app import agent_config
    @asynccontextmanager
    async def transport(endpoint, **kwargs):
        observed.append({'endpoint':endpoint,'headers':kwargs['headers']})
        yield object(),object(),None
    class Session:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        async def initialize(self):pass
        async def list_tools(self):
            return ListToolsResult(tools=[Tool(name='lookup',inputSchema={'type':'object','properties':{'vin':{'type':'string'}},'required':['vin']})])
        async def call_tool(self,name,arguments):
            observed.append({'name':name,'arguments':arguments})
            return CallToolResult(content=[TextContent(type='text',text='fake failure' if error else json.dumps({'vehicle':MODEL_NAME}))],isError=error)
    monkeypatch.setattr(agent_config,'streamablehttp_client',transport)
    monkeypatch.setattr(agent_config,'ClientSession',Session)
