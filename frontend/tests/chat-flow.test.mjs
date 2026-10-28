import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(fs.readFileSync(new URL('../src/lib/chat-flow.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const exports = {};
vm.runInThisContext(`(function(exports){${source}\n})`)(exports);
const { answerLandedAfter } = exports;

const user = { type: 'message', role: 'user', content: 'แสดงเก้าอี้' };
const tool = { type: 'function_call', call_id: 't1', name: 'search', arguments: '{}' };
const answerParts = { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'นี่คือ 3 ตัวครับ', annotations: [] }] };
const answerString = { type: 'message', role: 'assistant', content: 'นี่คือ 3 ตัวครับ' };
const emptyAnswer = { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: '  ', annotations: [] }] };

test('system events stay visible while the turn is still working', () => {
  assert.equal(answerLandedAfter([user, tool], 1), false);
  assert.equal(answerLandedAfter([user, tool, { type: 'function_call', call_id: 't2', name: 'x', arguments: '{}' }], 1), false);
  assert.equal(answerLandedAfter([user, tool, emptyAnswer], 1), false, 'blank assistant text does not count as an answer');
});

test('system events hide once the answer for the turn lands', () => {
  assert.equal(answerLandedAfter([user, tool, answerParts], 1), true);
  assert.equal(answerLandedAfter([user, tool, answerString], 1), true);
});

test('a new turn shows its own system events again', () => {
  const messages = [user, tool, answerParts, user, tool];
  assert.equal(answerLandedAfter(messages, 1), true, 'previous turn rows hidden');
  assert.equal(answerLandedAfter(messages, 4), false, 'current turn rows visible');
});
