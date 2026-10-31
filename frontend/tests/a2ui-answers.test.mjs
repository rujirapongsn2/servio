import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import React, { act } from 'react';
import { create } from 'react-test-renderer';
import { localModule } from './helpers/local-module.mjs';
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(path, mocks = {}) {
 const exports={}; const file=new URL('../'+path,import.meta.url);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInThisContext(`(function(require,exports){${code}\n})`)(name=>name in mocks?mocks[name]:localModule(name,file.pathname),exports);return exports;
}
const api=localModule('@/lib/a2ui-answers');
const discovery=localModule('@/lib/a2ui-discovery');
const SID='msg_answer1';
const data={text:'เปิด 09:00 น. ครับ',sources:[{title:'เวลาร้าน',excerpt:'เปิดทุกวัน 09:00–18:00'}],results:[{label:'lookup',columns:['รหัส','คงเหลือ'],rows:[['A01','0'],['A02','42']],truncated:false}]};
function snapshots(value=data) {return {[SID]:[
 {version:'v0.9.1',createSurface:{surfaceId:SID,catalogId:api.ANSWER_CATALOG}},
 {version:'v0.9.1',updateComponents:{surfaceId:SID,components:[{id:'root',component:'Answer',data:{path:'/answer'}}]}},
 {version:'v0.9.1',updateDataModel:{surfaceId:SID,path:'/answer',value}}
]};}

test('answers validate catalog, schema, bounds, sources and table data; reject action injection',()=>{
 assert.equal(api.parseAnswerSnapshots(snapshots())[SID].kind,'answer');
 assert.equal(discovery.parseA2uiSnapshots(snapshots())[SID].text,data.text);
 assert.ok(discovery.SUPPORTED_CATALOGS.includes(api.ANSWER_CATALOG));
 for(const mutate of [e=>e[SID][0].createSurface.catalogId='unknown',e=>e[SID][1].updateComponents.components[0].onClick={execute:'anything'},e=>e[SID][2].updateDataModel.surfaceId='other',e=>e[SID][2].version='v0.8']) {
  const e=snapshots();mutate(e);assert.deepEqual(Object.keys(api.parseAnswerSnapshots(e)),[]);
 }
 for(const value of [{...data,text:'x'.repeat(64001)},{...data,sources:[{title:'Source',excerpt:{html:'bad'}}]},{...data,results:[{...data.results[0],rows:[['missing cell']]}]}]) assert.deepEqual(Object.keys(api.parseAnswerSnapshots(snapshots(value))),[]);
});
const TextMessage=({text})=>React.createElement('p',{'data-answer-text':true},text);
const {AnswerSurface}=load('src/components/AnswerSurface.tsx',{'./messages/TextMessage':{TextMessage}});
const {ChatHistory}=load('src/components/ChatDialog.tsx',{
 'clsx':{default:(...values)=>values.filter(v=>typeof v==='string').join(' ')},
 '@/components/AnswerSurface':{AnswerSurface}, '@/components/MessageBubble':{MessageBubble:({message})=>React.createElement('p',null,typeof message.content==='string'?message.content:'fallback')},
 '@/components/ProductDiscovery':{ProductDiscovery:()=>React.createElement('div',{'data-discovery':true})},
});
for(const variant of ['page','widget']) test(`${variant}: answer once, sources, scrollable table and no execute controls`,async()=>{
 let renderer;const surface=api.parseAnswerSnapshots(snapshots())[SID];
 const props={locale:'th',messages:[{type:'message',role:'assistant',id:SID,content:data.text}],isLoading:false,a2uiSurfaces:{[SID]:surface},showSystemEvents:false};
 const render=()=>React.createElement('section',{'data-variant':variant},React.createElement(ChatHistory,props));
 await act(async()=>{renderer=create(render());});
 try {
  assert.equal(renderer.root.findAllByProps({'data-answer-text':true}).length,1);
  assert.equal(renderer.root.findAllByType('table').length,1);
  assert.equal(renderer.root.findAllByType('summary').length,2);
  assert.equal(renderer.root.findAllByType('button').length,0);
  assert.equal(renderer.root.findAllByProps({role:'region'})[0].props.tabIndex,0);
  assert.ok(JSON.stringify(renderer.toJSON()).includes('เวลาร้าน'));
  props.messages=[{...props.messages[0],id:'msg_unknown'}];await act(async()=>renderer.update(render()));
  assert.equal(renderer.root.findAllByProps({'data-answer-text':true}).length,0);
  assert.ok(JSON.stringify(renderer.toJSON()).includes(data.text));
 } finally {await act(async()=>renderer.unmount());}
});

test('single record, empty and truncated data have compact states',async()=>{
 let renderer;
 await act(async()=>{renderer=create(React.createElement(AnswerSurface,{surface:{kind:'answer',id:SID,...data,results:[{label:'lookup',columns:['status'],rows:[['ready']],truncated:true}]}}));});
 try {
  assert.equal(renderer.root.findAllByType('dl').length,1);
  assert.ok(JSON.stringify(renderer.toJSON()).includes('แสดงข้อมูลบางส่วน'));
  await act(async()=>renderer.update(React.createElement(AnswerSurface,{surface:{kind:'answer',id:SID,...data,results:[{label:'lookup',columns:['status'],rows:[],truncated:false}]}})));
  assert.ok(JSON.stringify(renderer.toJSON()).includes('ไม่พบข้อมูล'));
 }finally{await act(async()=>renderer.unmount());}
});

test('socket negotiates both catalogs, prevents answer actions and clears on reset',async()=>{
 const previous=globalThis.WebSocket;const sockets=[];
 class Socket {static OPEN=1;readyState=1;handlers={};sent=[];constructor(){sockets.push(this);}addEventListener(k,v){this.handlers[k]=v;}send(raw){this.sent.push(JSON.parse(raw));}close(){}emit(value){this.handlers.message({data:JSON.stringify(value)});}}
 globalThis.WebSocket=Socket;let state,renderer;
 const {useWebsocket}=load('src/hooks/useWebsocket.ts',{'@/lib/utils':{},'@/lib/api':{getWebsocketBaseUrl:()=> 'ws://test/ws'}});
 function Probe(){state=useWebsocket();return null;}
 await act(async()=>{renderer=create(React.createElement(Probe));});
 try {
  const socket=sockets[0];await act(async()=>socket.handlers.open());
  assert.ok(socket.sent[0].a2uiClientCapabilities.supportedCatalogIds.includes(api.ANSWER_CATALOG));
  await act(async()=>socket.emit({type:'history.updated',reason:'response.done',inputs:[{type:'message',role:'assistant',id:SID,content:data.text}],presentations:{},a2ui:snapshots()}));
  assert.equal(state.a2uiSurfaces[SID].text,data.text);
  assert.equal(state.sendDiscoveryAction(SID,{name:'discovery.refine',context:{color:'lighter',pattern:'similar'}}),false);
  assert.equal(state.history[0].content,data.text);
  await act(async()=>state.resetHistory());assert.deepEqual(Object.keys(state.a2uiSurfaces),[]);
 }finally{await act(async()=>renderer.unmount());globalThis.WebSocket=previous;}
});
