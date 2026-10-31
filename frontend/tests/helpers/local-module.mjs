import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = fileURLToPath(new URL('../../', import.meta.url));
const dependency = createRequire(import.meta.url);
const cache = new Map();
/** Load real local dependencies when an existing regression harness has no override. */
export function localModule(name, importer = path.join(root, 'src/index.ts')) {
  if (!name.startsWith('@/') && !name.startsWith('.')) return dependency(name);
  const base = name.startsWith('@/') ? path.join(root, 'src', name.slice(2)) : path.resolve(path.dirname(importer), name);
  if (base.endsWith('.css')) return { default: new Proxy({}, { get: (_, key) => String(key) }) };
  if (base.endsWith('.json')) return { default: JSON.parse(fs.readFileSync(base, 'utf8')) };
  const file = [base, base+'.ts', base+'.tsx'].find(value => fs.existsSync(value) && fs.statSync(value).isFile());
  if (!file) throw new Error('Local test module missing: '+name);
  if (cache.has(file)) return cache.get(file);
  const exports = {};
  cache.set(file, exports);
  const code = ts.transpileModule(fs.readFileSync(file,'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  vm.runInThisContext(`(function(require,exports){${code}\n})`, { filename:file })(request => localModule(request,file), exports);
  return exports;
}
