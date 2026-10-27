"use client";

import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Loader2, Maximize2, Minimize2, Plus, Trash2, Upload } from 'lucide-react';
import { useAdminLocale } from '@/lib/admin-locale';
import { getApiBaseUrl } from '@/lib/api';
import { emptyTable, nextColumnName, parseClipboardTable, parseTableDrafts, pasteTableCells, tableDraftIssue, TABLE_LIMITS, type TableDraft } from '@/lib/knowledge-tables';

const PAGE_SIZE = 50;
const buttonClass = 'inline-flex items-center justify-center gap-1 rounded-md border border-gray-300 px-2.5 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200';

export function KnowledgeTableEditor({ tables, onChange, disabled = false, readOnly = false, teamAgentId, onBusyChange, expanded = false, onToggleExpanded }: {
  tables: TableDraft[];
  onChange: (tables: TableDraft[]) => void;
  disabled?: boolean;
  readOnly?: boolean;
  teamAgentId?: number | null;
  onBusyChange?: (busy: boolean) => void;
  expanded?: boolean;
  onToggleExpanded?: () => void;
}) {
  const { copy } = useAdminLocale();
  const [selected, setSelected] = useState(tables[0]?.table_name ?? '');
  const [page, setPage] = useState(0);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const grid = useRef<HTMLTableElement>(null);
  const importController = useRef<AbortController | null>(null);
  const busyChange = useRef(onBusyChange);
  busyChange.current = onBusyChange;
  useEffect(() => { setImporting(false); return () => { importController.current?.abort(); busyChange.current?.(false); }; }, [teamAgentId]);
  const active = tables.find(table => table.table_name === selected) ?? tables[0];
  const locked = disabled || readOnly || importing;
  const pages = Math.max(1, Math.ceil((active?.rows.length ?? 0) / PAGE_SIZE));
  const currentPage = Math.min(page, pages - 1);
  const update = (next: TableDraft) => { setError(null); onChange(tables.map(table => table.table_name === next.table_name ? next : table)); };
  const uniqueName = () => { let index = 1; while (tables.some(table => table.table_name === `data_${index}`)) index++; return index; };

  const importFiles = async (files: FileList | null) => {
    if (!files?.length || locked) return;
    if (Array.from(files).some(file => !/\.(csv|xlsx)$/i.test(file.name)) || Array.from(files).reduce((size, file) => size + file.size, 0) > TABLE_LIMITS.bytes) { setError(copy.tableLimitIssue); return; }
    const controller = new AbortController(); importController.current = controller;
    setImporting(true); busyChange.current?.(true); setError(null);
    try {
      const form = new FormData(); Array.from(files).forEach(file => form.append('files', file));
      const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : '';
      const response = await fetch(`${getApiBaseUrl()}/api/admin/okf-bundles/table-drafts/import${params}`, { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('adminToken')}` }, body: form, signal: controller.signal });
      const payload: unknown = await response.json();
      if (!response.ok || !payload || typeof payload !== 'object' || !('tables' in payload)) throw new Error(copy.tableDataIssue);
      if (controller.signal.aborted) return;
      const imported = parseTableDrafts(payload.tables);
      const existing = tables.length === 1 && tables[0].rows.every(row => row.every(cell => !cell)) && tables[0].columns.every((column, index) => column === `Column ${index + 1}`) ? [] : tables;
      let index = 1; const used = new Set(existing.map(table => table.table_name));
      const next = [...existing, ...imported.map(table => { while (used.has(`data_${index}`)) index++; const table_name = `data_${index++}`; used.add(table_name); return { ...table, table_name }; })];
      if (tableDraftIssue(next, false)) throw new Error(copy.tableLimitIssue);
      onChange(next); setSelected(next[existing.length]?.table_name ?? ''); setPage(0);
    } catch (err) { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : copy.tableDataIssue); }
    finally { if (!controller.signal.aborted) { setImporting(false); busyChange.current?.(false); } }
  };

  if (!active) return null;
  return <section className="min-w-0 space-y-3" aria-label={copy.tables}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto" role="tablist" aria-label={copy.tables}>
        {tables.map(table => <button key={table.table_name} type="button" role="tab" aria-selected={active.table_name === table.table_name} onClick={() => { setSelected(table.table_name); setPage(0); }} className={`${buttonClass} shrink-0 ${active.table_name === table.table_name ? 'border-emerald-500 bg-emerald-50 text-emerald-800' : ''}`}>{table.name}</button>)}
      </div>
      <div className="flex flex-wrap gap-2">
        {onToggleExpanded && <button type="button" className={buttonClass} aria-expanded={expanded} onClick={onToggleExpanded} title={expanded ? copy.shrinkTable : copy.expandTable}>
          {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}{expanded ? copy.shrinkTable : copy.expandTable}
        </button>}
      {!readOnly && <>
        <button type="button" className={buttonClass} disabled={locked || tables.length >= TABLE_LIMITS.tables} onClick={() => { const next = emptyTable(uniqueName()); onChange([...tables, next]); setSelected(next.table_name); setPage(0); }}><Plus className="h-4 w-4" />{copy.addTable}</button>
        <label className={`${buttonClass} ${locked ? 'opacity-50' : 'cursor-pointer'}`}>
          {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}{copy.importTableFile}
          <input type="file" accept=".xlsx,.csv" multiple className="sr-only" aria-label={copy.importTableFile} disabled={locked} onChange={event => { const files = event.target.files; void importFiles(files); event.currentTarget.value = ''; }} />
        </label>
      </>}
      </div>
    </div>
    <div className="flex flex-wrap items-end gap-2">
      <label className="min-w-0 flex-1 text-xs font-medium text-gray-600 dark:text-gray-300">{copy.tableName}<input className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800" value={active.name} disabled={locked} onChange={event => update({ ...active, name: event.target.value })} /></label>
      {!readOnly && <button type="button" className={buttonClass} disabled={locked || tables.length <= 1} onClick={() => { if (!window.confirm(copy.tableDiscard)) return; onChange(tables.filter(table => table.table_name !== active.table_name)); setPage(0); }}><Trash2 className="h-4 w-4" />{copy.removeTable}</button>}
    </div>
    <div className={`${expanded ? "max-h-[70dvh]" : "max-h-[55vh]"} overflow-auto rounded-lg border border-gray-300 dark:border-gray-600`}>
      <table ref={grid} className="w-full border-collapse text-sm" aria-label={active.name}>
        <thead className="sticky top-0 z-10 bg-gray-100 dark:bg-gray-800"><tr><th scope="col" className="sticky left-0 z-20 w-12 bg-gray-100 px-2 py-2 dark:bg-gray-800">#</th>{active.columns.map((column, col) => <th scope="col" key={col} className="min-w-40 border-l border-gray-200 px-1 py-1 dark:border-gray-700">
          <div className="flex items-center"><input size={1} aria-label={copy.tableHeader(col + 1)} value={column} disabled={locked} className="min-w-0 flex-1 bg-transparent px-2 py-2 font-semibold outline-none focus:bg-white focus:ring-2 focus:ring-inset focus:ring-emerald-500 dark:focus:bg-gray-900" onChange={event => update({ ...active, columns: active.columns.map((value, index) => index === col ? event.target.value : value) })} />
          {!readOnly && <button type="button" title={copy.removeColumn} aria-label={`${copy.removeColumn} ${col + 1}`} className="rounded p-1 text-gray-400 hover:text-red-600 disabled:opacity-30" disabled={locked || active.columns.length <= 1} onClick={() => update({ ...active, columns: active.columns.filter((_, index) => index !== col), rows: active.rows.map(row => row.filter((_, index) => index !== col)) })}><Trash2 className="h-3.5 w-3.5" /></button>}</div>
        </th>)}{!readOnly && <th scope="col" className="w-10" />}</tr></thead>
        <tbody>{active.rows.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map((row, localRow) => {
          const rowIndex = currentPage * PAGE_SIZE + localRow;
          return <tr key={rowIndex}><th scope="row" className="sticky left-0 bg-gray-50 px-2 text-xs font-normal text-gray-500 dark:bg-gray-900">{rowIndex + 1}</th>{active.columns.map((column, col) => <td key={col} className="border-l border-t border-gray-200 p-0 dark:border-gray-700">
            <input size={1} data-row={rowIndex} data-column={col} aria-label={copy.tableCell(column || copy.tableHeader(col + 1), rowIndex + 1)} value={row[col] ?? ''} readOnly={readOnly} disabled={disabled || importing} className="min-w-40 w-full bg-white px-3 py-2 outline-none focus:bg-emerald-50 focus:ring-2 focus:ring-inset focus:ring-emerald-500 dark:bg-gray-900 dark:focus:bg-gray-800" onChange={event => update({ ...active, rows: active.rows.map((value, index) => index === rowIndex ? value.map((cell, c) => c === col ? event.target.value : cell) : value) })}
              onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); grid.current?.querySelector<HTMLInputElement>(`input[data-row="${rowIndex + (event.shiftKey ? -1 : 1)}"][data-column="${col}"]`)?.focus(); } }}
              onPaste={event => { if (locked) return; const text = event.clipboardData.getData('text/plain'); if (!/[\t\r\n]/.test(text)) return; event.preventDefault(); try { update(pasteTableCells(active, rowIndex, col, parseClipboardTable(text))); } catch { setError(copy.tableLimitIssue); } }} />
          </td>)}{!readOnly && <td className="border-t border-gray-200 px-1 dark:border-gray-700"><button type="button" aria-label={copy.deleteTableRow(rowIndex + 1)} title={copy.deleteTableRow(rowIndex + 1)} disabled={locked} className="rounded p-1 text-gray-400 hover:text-red-600" onClick={() => update({ ...active, rows: active.rows.filter((_, index) => index !== rowIndex) })}><Trash2 className="h-4 w-4" /></button></td>}</tr>;
        })}</tbody>
      </table>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-2">
      {!readOnly ? <div className="flex gap-2"><button type="button" className={buttonClass} disabled={locked || active.rows.length >= TABLE_LIMITS.rows} onClick={() => { update({ ...active, rows: [...active.rows, active.columns.map(() => '')] }); setPage(Math.floor(active.rows.length / PAGE_SIZE)); }}><Plus className="h-4 w-4" />{copy.addRow}</button><button type="button" className={buttonClass} disabled={locked || active.columns.length >= TABLE_LIMITS.columns} onClick={() => update({ ...active, columns: [...active.columns, nextColumnName(active.columns)], rows: active.rows.map(row => [...row, '']) })}><Plus className="h-4 w-4" />{copy.addColumn}</button></div> : <span className="text-xs text-gray-500">{copy.tableReadOnly}</span>}
      <div className="flex items-center gap-2 text-xs text-gray-500"><span>{copy.tableDimensions(active.rows.length, active.columns.length)}</span><button type="button" className={buttonClass} aria-label={copy.tablePrevious} disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft className="h-4 w-4" /></button><span>{copy.tablePage(currentPage + 1, pages)}</span><button type="button" className={buttonClass} aria-label={copy.tableNext} disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}><ChevronRight className="h-4 w-4" /></button></div>
    </div>
    <details className="text-xs leading-5 text-gray-500 dark:text-gray-400">
      <summary className="cursor-pointer rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-500">{copy.tableLimitsSummary(TABLE_LIMITS.rows)}</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>{copy.tableLimitsStructure(TABLE_LIMITS.columns, TABLE_LIMITS.tables, TABLE_LIMITS.cells, TABLE_LIMITS.bytes / 1024 / 1024)}</li>
        <li>{copy.tableLimitsSpeed}</li>
        <li>{copy.tableLimitsResults}</li>
        <li>{copy.tableLimitsAccuracy}</li>
      </ul>
    </details>
    {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
  </section>;
}
