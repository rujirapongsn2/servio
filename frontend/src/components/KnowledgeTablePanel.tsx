"use client";

import { useEffect, useRef, useState } from 'react';
import { Loader2, RefreshCw, Save } from 'lucide-react';
import { useAdminLocale } from '@/lib/admin-locale';
import { getApiBaseUrl } from '@/lib/api';
import { parseTableWorkbook, tableDraftIssue, type TableDraft, type TableWorkbook } from '@/lib/knowledge-tables';
import { KnowledgeTableEditor } from '@/components/KnowledgeTableEditor';

export function KnowledgeTablePanel({ bundleId, teamAgentId, canEdit, onDirtyChange, onSaved, expanded = false, onToggleExpanded }: {
  bundleId: number;
  teamAgentId?: number | null;
  canEdit: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onSaved?: () => void;
  expanded?: boolean;
  onToggleExpanded?: () => void;
}) {
  const { copy } = useAdminLocale();
  const [saved, setSaved] = useState<TableWorkbook | null>(null);
  const [tables, setTables] = useState<TableDraft[]>([]);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState(false);
  const reloadController = useRef<AbortController | null>(null);
  const dirtyChange = useRef(onDirtyChange);
  dirtyChange.current = onDirtyChange;
  useEffect(() => { dirtyChange.current(dirty); }, [dirty]);
  useEffect(() => () => { dirtyChange.current(false); }, []);
  useEffect(() => {
    if (!dirty || typeof window === 'undefined') return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const url = `${getApiBaseUrl()}/api/admin/okf-bundles/${bundleId}/tables${teamAgentId ? `?team_agent_id=${teamAgentId}` : ''}`;
  const load = async () => {
    reloadController.current?.abort(); const controller = new AbortController(); reloadController.current = controller;
    setLoading(true); setError(null); setMessage(false);
    try {
      const response = await fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem('adminToken')}` }, signal: controller.signal });
      if (!response.ok) throw new Error(copy.tableDataIssue);
      const value = parseTableWorkbook(await response.json());
      if (!controller.signal.aborted) { setSaved(value); setTables(value.tables); setDirty(false); }
    } catch (err) { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : copy.tableDataIssue); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  };
  useEffect(() => { void load(); return () => reloadController.current?.abort(); }, [url]);
  const save = async () => {
    if (!saved || !canEdit || !saved.can_edit || saving || importing) return;
    const issue = tableDraftIssue(tables, false);
    if (issue) { setError(issue === 'limits' ? copy.tableLimitIssue : copy.tableDataIssue); return; }
    setSaving(true); setError(null); setMessage(false);
    try {
      const response = await fetch(url, { method: 'PUT', headers: { Authorization: `Bearer ${localStorage.getItem('adminToken')}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: saved.revision, tables }) });
      if (!response.ok) throw new Error(response.status === 409 ? copy.tableConflict : copy.tableDataIssue);
      const next = parseTableWorkbook(await response.json());
      setSaved(next); setTables(next.tables); setDirty(false); setMessage(true); onSaved?.();
    } catch (err) { setError(err instanceof Error ? err.message : copy.tableDataIssue); }
    finally { setSaving(false); }
  };
  if (loading) return <div className="flex items-center gap-2 py-8 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" />{copy.tableLoading}</div>;
  return <div className="min-w-0 space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span role="status" className="text-xs text-gray-500">{message ? copy.tableSaved : dirty ? copy.tableUnsaved : ''}</span>
      <div className="flex flex-wrap gap-2"><button type="button" disabled={saving || importing} className="inline-flex items-center gap-1 rounded-md border px-3 py-2 text-sm disabled:opacity-50" onClick={() => { if (!dirty || window.confirm(copy.tableDiscard)) void load(); }}><RefreshCw className="h-4 w-4" />{copy.reloadTables}</button>
      {canEdit && saved?.can_edit && <><button type="button" disabled={!dirty || saving || importing} className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" onClick={() => { if (saved) { setTables(saved.tables); setDirty(false); setError(null); setMessage(false); } }}>{copy.cancel}</button><button type="button" disabled={!dirty || saving || importing} onClick={() => { void save(); }} className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-2 text-sm text-white disabled:opacity-50">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}{copy.saveTables}</button></>}
      </div>
    </div>
    {saved && <KnowledgeTableEditor expanded={expanded} onToggleExpanded={onToggleExpanded} tables={tables} onChange={next => { setTables(next); setDirty(true); setMessage(false); }} teamAgentId={teamAgentId} onBusyChange={setImporting} disabled={saving} readOnly={!canEdit || !saved.can_edit} />}
    {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
  </div>;
}
