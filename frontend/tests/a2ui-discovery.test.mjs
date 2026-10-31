import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import React, { act } from 'react';
import { create } from 'react-test-renderer';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(path, mocks = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(new URL('../'+path, import.meta.url),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  const require = name => {
    if (name in mocks) return mocks[name];
    if (name === 'react') return React;
    throw new Error('Missing '+name);
  };
  vm.runInThisContext(`(function(require,exports){${code}\n})`)(require,exports);
  return exports;
}
// Use the real JSX runtime, parser and catalog component in both presentation variants.
import * as runtime from 'react/jsx-runtime';
const productApi = load('src/lib/product-presentations.ts');
const api = load('src/lib/a2ui-discovery.ts', {'./product-presentations':productApi, './a2ui-discovery.catalog.json':{__esModule:true,default:JSON.parse(fs.readFileSync(new URL('../src/lib/a2ui-discovery.catalog.json',import.meta.url),'utf8'))}});
const SID='msg_'+'a'.repeat(32);
const products = [1,2,3,4].map(n=>({id:String(n).repeat(32),asset_id:String(n).repeat(64),title:'สินค้า '+n,source_label:'long-original-file-'+n+'.jpg',description:'ลายไม้และโทนสีใกล้เคียง',image_url:'/api/knowledge-images/'+String(n).repeat(64)+'?token=test',part_number:'WY'+n,brand:'Tak'}));
const envelopes = (change={}) => ({[SID]:[
 {version:api.A2UI_VERSION,createSurface:{surfaceId:SID,catalogId:api.DISCOVERY_CATALOG}},
 {version:api.A2UI_VERSION,updateComponents:{surfaceId:SID,components:[{id:'root',component:'ProductDiscovery',data:{path:'/discovery'},refineAction:{event:{name:'discovery.refine'}},inquireAction:{event:{name:'discovery.inquire'}}}]}},
 {version:api.A2UI_VERSION,updateDataModel:{surfaceId:SID,path:'/discovery',value:{active:true,summary:'ใกล้เคียง ยังไม่ยืนยันรุ่นเดียวกัน',products,filters:{color:'similar',pattern:'similar'},queryImage:'data:image/jpeg;base64,YQ==',...change}}}
]});

test('A2UI snapshot validates version, catalog, root, IDs, assets and filters',()=>{
 assert.equal(api.parseDiscoverySnapshots(envelopes())[SID].products.length,4);
 for (const mutate of [e=>{e[SID][0].version='v0.8'},e=>{e[SID][0].createSurface.catalogId='other'},e=>{e[SID][1].updateComponents.components[0].component='Script'},e=>{e[SID][2].updateDataModel.surfaceId='other'}]) {
  const e=envelopes();mutate(e);assert.equal(Object.keys(api.parseDiscoverySnapshots(e)).length,0);
 }
 for(const data of [{filters:{color:'red',pattern:'similar'}},{queryImage:'javascript:alert(1)'},{products:[{...products[0],image_url:'https://evil.test/image.jpg'}]}]) assert.equal(Object.keys(api.parseDiscoverySnapshots(envelopes(data))).length,0);
});
test('no-match snapshot remains interactive with no stale cards',()=>{
 const parsed=api.parseDiscoverySnapshots(envelopes({products:[],summary:'ไม่พบสินค้าตามเงื่อนไข'}))[SID];
 assert.equal(parsed.products.length,0);assert.equal(parsed.active,true);
});

const css={__esModule:true,default:new Proxy({}, {get:(_,key)=>String(key)})};
const {ProductCarousel}=load('src/components/ProductCarousel.tsx',{'react/jsx-runtime':runtime,'@/lib/api':{buildApiUrl:x=>x}});
const {ProductDiscovery}=load('src/components/ProductDiscovery.tsx',{'react/jsx-runtime':runtime,'./ProductCarousel':{ProductCarousel},'@/lib/api':{buildApiUrl:x=>x},'@/lib/a2ui-discovery':api,'./ProductDiscovery.module.css':css});

for (const variant of ['page','widget']) test(`${variant}: filter actions, bounded comparison, selected inquiry and empty recovery`,async()=>{
 let surface=api.parseDiscoverySnapshots(envelopes())[SID];const actions=[];let renderer;
 const props=()=>({surface,disabled:false,onAction:(id,action)=>{actions.push({id,action});return true;}});
 const render=()=>React.createElement('section',{'data-variant':variant},React.createElement(ProductDiscovery,props()));
 await act(async()=>{renderer=create(render(),{createNodeMock:element=>element.type==='dialog'?{open:false,showModal(){this.open=true},close(){this.open=false}}:element.type==='button'?{focus(){}}:null});});
 try {
  const select=renderer.root.findAllByType('select');
  await act(async()=>select[0].props.onChange({target:{value:'lighter'}}));
  await act(async()=>select[1].props.onChange({target:{value:'wood_grain'}}));
  await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.deepEqual(actions[0],{id:SID,action:{name:'discovery.refine',context:{color:'lighter',pattern:'wood_grain'}}});
  const boxes=()=>renderer.root.findAllByType('input').filter(n=>n.props.type==='checkbox');
  for(let i=0;i<3;i++) await act(async()=>boxes()[i].props.onChange());
  assert.equal(boxes()[3].props.disabled,true);
  const compare=()=>renderer.root.findAllByType('button').find(n=>n.props.children?.[0]==='เปรียบเทียบ');
  await act(async()=>compare().props.onClick());
  const dialog=renderer.root.findAllByType('dialog').find(n=>n.props.className==='dialog');assert.equal(dialog.findAllByType('article').length,3);
  await act(async()=>dialog.findAllByType('button').find(n=>n.props.children==='สอบถามสินค้านี้').props.onClick());
  assert.deepEqual(actions[1],{id:SID,action:{name:'discovery.inquire',context:{card_id:products[0].id}}});
  surface=api.parseDiscoverySnapshots(envelopes({products:[],summary:'ไม่พบสินค้าตามเงื่อนไข'}))[SID];
  await act(async()=>renderer.update(render()));
  assert.equal(boxes().length,0);assert.equal(renderer.root.findAllByType('select').length,2);
  assert.equal(renderer.root.findAllByType('select')[0].props.disabled,false);
  surface={...surface,active:false};await act(async()=>renderer.update(render()));
  assert.equal(renderer.root.findAllByType('select')[0].props.disabled,true);
 } finally {await act(async()=>renderer.unmount());}
});

test('socket negotiates A2UI, correlates filters, prevents duplicate actions and keeps image drafts independent',async()=>{
 const previous=globalThis.WebSocket;
 const sockets=[];
 class Socket {
  static OPEN=1;
  readyState=1; handlers={}; sent=[];
  constructor(){sockets.push(this);}
  addEventListener(name,handler){this.handlers[name]=handler;}
  send(raw){this.sent.push(JSON.parse(raw));}
  close(){}
  emit(event){this.handlers.message({data:JSON.stringify(event)});}
 }
 globalThis.WebSocket=Socket;
 const {useWebsocket}=load('src/hooks/useWebsocket.ts',{'@/lib/a2ui-discovery':api,'@/lib/product-presentations':productApi,'@/lib/utils':{},'@/lib/api':{getWebsocketBaseUrl:()=> 'ws://test/ws'}});
 let state,renderer;
 function Probe(){state=useWebsocket();return null;}
 await act(async()=>{renderer=create(React.createElement(Probe));});
 try {
  const socket=sockets[0];await act(async()=>socket.handlers.open());
  assert.equal(socket.sent[0].type,'a2ui.capabilities');
  await act(async()=>socket.emit({type:'history.updated',reason:'assistant.message',inputs:[{type:'message',role:'assistant',id:SID,content:'ใกล้เคียง'}],presentations:{},a2ui:envelopes()}));
  let first,duplicate;
  await act(async()=>{
   first=state.sendDiscoveryAction(SID,{name:'discovery.refine',context:{color:'darker',pattern:'similar'}});
   duplicate=state.sendDiscoveryAction(SID,{name:'discovery.refine',context:{color:'darker',pattern:'similar'}});
  });
  assert.equal(first,true);assert.equal(duplicate,false);
  const request=socket.sent.at(-1);
  assert.equal(request.action.surfaceId,SID);assert.equal(request.version,'v0.9.1');
  assert.equal(JSON.stringify(request).includes('base64'),false);
  await act(async()=>socket.emit({type:'knowledge.image.error',request_id:'stale-request',message:'ignore'}));
  assert.equal(state.isLoading,true);
  await act(async()=>socket.emit({type:'knowledge.image.error',request_id:request.request_id,message:'ลองใหม่',retryable:true}));
  assert.equal(state.isLoading,false);assert.equal(state.productActionError,'ลองใหม่');
  assert.equal(state.imageSearchState.kind,'idle');
  await act(async()=>state.resetHistory());
  assert.equal(Object.keys(state.a2uiSurfaces).length,0);
  assert.equal(state.sendDiscoveryAction(SID,{name:'discovery.inquire',context:{card_id:products[0].id}}),false);
 }finally{await act(async()=>renderer.unmount());globalThis.WebSocket=previous;}
});
