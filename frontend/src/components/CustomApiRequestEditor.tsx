"use client";

import { useId, useRef, useState } from 'react';
import { methods, parseCurl, type Parameter, type RequestDraft } from '@/lib/custom-api';

const inputClass = 'w-full min-w-0 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white';
const buttonClass = 'rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600';

const panels = ['query', 'headers', 'body'] as const;
type Panel = typeof panels[number];

const isCredential = (name: string) => /authorization|api.?key|token|secret|cookie|password/i.test(name);

function ParameterRows({ label, value, onChange }: { label: string; value: Parameter[]; onChange: (value: Parameter[]) => void }) {
  const id = useId();
  const [revealed, setRevealed] = useState(false);
  const rowLabel = label === 'Headers' ? 'Header' : label === 'Query parameters' ? 'Query parameter' : 'Form parameter';
  return <fieldset className="min-w-0 space-y-2">
    <legend className="sr-only">{label}</legend>
    {value.length > 0 && <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] gap-2 text-xs font-medium" aria-hidden="true"><span>Name</span><span>Value</span><span className="w-9" /></div>}
    {value.map((row, index) => <div key={index} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] items-end gap-2">
      <div className="min-w-0"><label htmlFor={`${id}-name-${index}`} className="sr-only">{rowLabel} name {index + 1}</label><input id={`${id}-name-${index}`} className={inputClass} required value={row.name} onChange={e => onChange(value.map((item, i) => i === index ? { ...item, name: e.target.value } : item))} /></div>
      <div className="min-w-0"><label htmlFor={`${id}-value-${index}`} className="sr-only">{rowLabel} value {index + 1}</label><input id={`${id}-value-${index}`} className={inputClass} type={isCredential(row.name) && !revealed ? 'password' : 'text'} autoComplete="off" value={row.value} onChange={e => onChange(value.map((item, i) => i === index ? { ...item, value: e.target.value } : item))} /></div>
      <button type="button" className={buttonClass + ' mb-0.5'} aria-label={`Remove ${label.toLowerCase()} ${index + 1}`} title="Remove" onClick={() => onChange(value.filter((_, i) => i !== index))}>×</button>
    </div>)}
    <div className="flex flex-wrap items-center gap-3"><button type="button" className={buttonClass} onClick={() => onChange([...value, { name: '', value: '' }])}>+ Add {label === 'Headers' ? 'header' : 'parameter'}</button>
      {value.some(row => isCredential(row.name)) && <button type="button" className="text-sm underline" onClick={() => setRevealed(!revealed)}>{revealed ? 'Hide' : 'Show'} values</button>}
    </div>
  </fieldset>;
}

export default function CustomApiRequestEditor({ value, onChange }: { value: RequestDraft; onChange: (draft: RequestDraft) => void }) {
  const id = useId();
  const [activePanel, setActivePanel] = useState<Panel>(value.bodyKind !== 'none' ? 'body' : 'query');
  const tabRefs = useRef<Record<Panel, HTMLButtonElement | null>>({ query: null, headers: null, body: null });
  const [command, setCommand] = useState('');
  const [preview, setPreview] = useState<RequestDraft | null>(null);
  const [error, setError] = useState('');
  const update = (patch: Partial<RequestDraft>) => onChange({ ...value, ...patch });
  return <div className="min-w-0 space-y-5 text-gray-900 dark:text-white">
    <details className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
      <summary className="cursor-pointer text-sm font-medium">Import cURL</summary>
      <div className="mt-3 space-y-3">
        <label htmlFor={`${id}-curl`} className="block text-sm">cURL command</label>
        <textarea id={`${id}-curl`} className={inputClass + ' font-mono'} rows={4} autoComplete="off" spellCheck={false} value={command} onChange={e => { setCommand(e.target.value); setPreview(null); setError(''); }} />
        <button type="button" className={buttonClass} onClick={() => { try { setPreview(parseCurl(command)); setError(''); } catch (error) { setPreview(null); setError(error instanceof Error ? error.message : 'Unable to parse cURL.'); } }}>Parse cURL</button>
        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        {preview && <div className="rounded bg-gray-50 p-3 dark:bg-gray-900 space-y-2">
          <p className="text-sm">Ready to apply: {preview.method} · {preview.headers.length} headers · {preview.query.length} query parameters · {preview.bodyKind} body</p>
          <p className="text-xs text-gray-500">Replaces request fields. Review them before saving.</p>
          <button type="button" className={buttonClass} onClick={() => { onChange(preview); setActivePanel(preview.bodyKind !== 'none' ? 'body' : preview.query.length ? 'query' : preview.headers.length ? 'headers' : 'query'); setPreview(null); setCommand(''); }}>Apply request</button>
        </div>}
      </div>
    </details>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
      <div><label htmlFor={`${id}-method`} className="block text-sm font-medium mb-1">Method</label><select id={`${id}-method`} className={inputClass} value={value.method} onChange={e => update({ method: e.target.value })}>{methods.map(method => <option key={method}>{method}</option>)}</select></div>
      <div><label htmlFor={`${id}-url`} className="block text-sm font-medium mb-1">Request URL</label><input id={`${id}-url`} className={inputClass} type="url" required autoComplete="off" value={value.endpoint} onChange={e => update({ endpoint: e.target.value })} /></div>
    </div>
    <div className="min-w-0 space-y-3">
      <div role="tablist" aria-label="Request parameters" className="flex min-w-0 gap-1 border-b border-gray-200 dark:border-gray-700">
        {panels.map(panel => <button key={panel} type="button" role="tab" id={`${id}-tab-${panel}`} aria-controls={`${id}-panel-${panel}`} aria-selected={activePanel === panel} tabIndex={activePanel === panel ? 0 : -1} ref={node => { tabRefs.current[panel] = node; }} className={`min-w-0 border-b-2 px-3 py-2 text-sm font-medium ${activePanel === panel ? 'border-blue-600 text-blue-700 dark:text-blue-400' : 'border-transparent text-gray-600 dark:text-gray-400'}`} onClick={() => setActivePanel(panel)} onKeyDown={event => {
          const index = panels.indexOf(panel);
          const next = event.key === 'ArrowRight' ? panels[(index + 1) % panels.length] : event.key === 'ArrowLeft' ? panels[(index + panels.length - 1) % panels.length] : event.key === 'Home' ? panels[0] : event.key === 'End' ? panels[panels.length - 1] : null;
          if (next) { event.preventDefault(); setActivePanel(next); tabRefs.current[next]?.focus(); }
        }}>{panel === 'query' ? `Query (${value.query.length})` : panel === 'headers' ? `Headers (${value.headers.length})` : 'Body'}</button>)}
      </div>
      <div key={activePanel} role="tabpanel" id={`${id}-panel-${activePanel}`} aria-labelledby={`${id}-tab-${activePanel}`} tabIndex={0} className="min-w-0">
        {activePanel === 'query' && <ParameterRows label="Query parameters" value={value.query} onChange={query => update({ query })} />}
        {activePanel === 'headers' && <ParameterRows label="Headers" value={value.headers} onChange={headers => update({ headers })} />}
        {activePanel === 'body' && <div className="min-w-0 space-y-2">
      <label htmlFor={`${id}-body-kind`} className="block text-sm font-medium">Body format</label>
      <select id={`${id}-body-kind`} className={inputClass} value={value.bodyKind} onChange={e => { const kind = e.target.value; if (kind === 'none' || kind === 'json' || kind === 'text' || kind === 'form') update({ bodyKind: kind }); }}>
        <option value="none">None</option><option value="json">JSON</option><option value="text">Raw text</option><option value="form">Form URL encoded</option>
      </select>
      {value.bodyKind === 'form' ? <ParameterRows label="Form parameters" value={value.fields} onChange={fields => update({ fields })} /> : value.bodyKind !== 'none' && <><label htmlFor={`${id}-body`} className="block text-sm">{value.bodyKind === 'json' ? 'JSON body' : 'Text body'}</label><textarea id={`${id}-body`} className={inputClass + ' font-mono resize-y'} rows={8} spellCheck={false} autoComplete="off" value={value.bodyText} onChange={e => update({ bodyText: e.target.value })} /></>}
      <p className="text-xs text-gray-500 dark:text-gray-400">Use {'{{query}}'} where the agent’s input belongs.</p>
    </div>}
      </div>
    </div>
    <details className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
      <summary className="cursor-pointer text-sm font-medium">Authentication & timeout</summary>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
        <div><label htmlFor={`${id}-token`} className="block text-sm mb-1">Bearer token (optional)</label><input id={`${id}-token`} className={inputClass} type="password" autoComplete="new-password" value={value.auth_token} onChange={e => update({ auth_token: e.target.value })} /></div>
        <div><label htmlFor={`${id}-timeout`} className="block text-sm mb-1">Timeout (seconds)</label><input id={`${id}-timeout`} className={inputClass} type="number" required min={0} step="any" value={value.timeout_seconds} onChange={e => update({ timeout_seconds: e.target.value })} /></div>
      </div>
    </details>
  </div>;
}
