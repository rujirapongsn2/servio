import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependency = createRequire(import.meta.url);
function load(file, mocks = {}) {
  const filename = path.join(root, file);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })((name) => Object.hasOwn(mocks, name) ? mocks[name] : dependency(name), exports);
  return exports;
}
export const { adminCopy } = load('src/lib/admin-copy.ts');
export const adminLocale = load('src/lib/admin-locale.tsx', { '@/lib/admin-copy': { adminCopy } });
export function EnglishAdminLocale({ children }) {
  return React.createElement(adminLocale.AdminLocaleContext.Provider, { value: { locale: 'en', copy: adminCopy.en, setLocale() {} } }, children);
}
export function ThaiAdminLocale({ children }) {
  return React.createElement(adminLocale.AdminLocaleContext.Provider, { value: { locale: 'th', copy: adminCopy.th, setLocale() {} } }, children);
}
export function SwitchableAdminLocale({ children, onReady }) {
  const [locale, setLocale] = React.useState('en');
  onReady(setLocale);
  return React.createElement(adminLocale.AdminLocaleContext.Provider, { value: { locale, copy: adminCopy[locale], setLocale } }, children);
}
