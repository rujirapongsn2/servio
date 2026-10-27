export type TableDraft = { table_name: string; name: string; columns: string[]; rows: string[][] };
export type TableWorkbook = { revision: string; tables: TableDraft[]; can_edit: boolean };
export const TABLE_LIMITS = { rows: 19_999, columns: 200, cells: 2_000_000, tables: 50, bytes: 50 * 1024 * 1024 };

export function emptyTable(index = 1): TableDraft {
  return { table_name: `data_${index}`, name: `Table ${index}`, columns: ['Column 1', 'Column 2', 'Column 3'], rows: Array.from({ length: 3 }, () => ['', '', '']) };
}

export function parseTableDrafts(value: unknown): TableDraft[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > TABLE_LIMITS.tables) throw new Error('Invalid table data');
  const result = value.map((table): TableDraft => {
    if (!table || typeof table !== 'object' || !('table_name' in table) || typeof table.table_name !== 'string' || !/^data_[1-9][0-9]*$/.test(table.table_name) || !('name' in table) || typeof table.name !== 'string' || !('columns' in table) || !Array.isArray(table.columns) || !table.columns.every((cell: unknown): cell is string => typeof cell === 'string') || !('rows' in table) || !Array.isArray(table.rows)) throw new Error('Invalid table data');
    const columns = table.columns;
    const rows = table.rows.map((row: unknown): string[] => {
      if (!Array.isArray(row) || row.length !== columns.length || !row.every((cell: unknown): cell is string => typeof cell === 'string')) throw new Error('Invalid table cells');
      return row;
    });
    return { table_name: table.table_name, name: table.name, columns, rows };
  });
  if (tableDraftIssue(result, false)) throw new Error('Table data exceeds its limits');
  return result;
}

export function parseTableWorkbook(value: unknown): TableWorkbook {
  if (!value || typeof value !== 'object' || !('revision' in value) || typeof value.revision !== 'string' || !value.revision || !('tables' in value) || !('can_edit' in value) || typeof value.can_edit !== 'boolean') throw new Error('Invalid workbook response');
  return { revision: value.revision, tables: parseTableDrafts(value.tables), can_edit: value.can_edit };
}

export function tableDraftIssue(tables: TableDraft[], requireData = true): 'structure' | 'headers' | 'empty' | 'limits' | null {
  if (!tables.length || tables.length > TABLE_LIMITS.tables || new Set(tables.map(table => table.table_name)).size !== tables.length) return 'structure';
  let rows = 0, cells = 0;
  for (const table of tables) {
    if (!table.name.trim() || !table.columns.length || table.rows.some(row => row.length !== table.columns.length)) return 'structure';
    if (table.columns.some(column => !column.trim() || new TextEncoder().encode(column).length > 256) || new Set(table.columns.map(column => column.trim().toLowerCase())).size !== table.columns.length) return 'headers';
    if (requireData && !table.rows.some(row => row.some(cell => cell.trim()))) return 'empty';
    rows += table.rows.length; cells += table.rows.length * table.columns.length;
    if (table.columns.length > TABLE_LIMITS.columns || rows > TABLE_LIMITS.rows || cells > TABLE_LIMITS.cells || table.rows.some(row => row.some(cell => cell.includes('\0') || new TextEncoder().encode(cell).length > 32768))) return 'limits';
  }
  if (new TextEncoder().encode(JSON.stringify(tables)).length > TABLE_LIMITS.bytes) return 'limits';
  return null;
}

export function tablesToFiles(tables: TableDraft[]): File[] {
  if (tableDraftIssue(tables)) throw new Error('Check table names, headers, data and limits before saving');
  const quote = (value: string) => `"${value.replaceAll('"', '""')}"`;
  const used = new Set<string>();
  return tables.map((table) => {
    const text = '\ufeff' + [table.columns, ...table.rows.filter(row => row.some(cell => cell.trim()))].map(row => row.map(quote).join(',')).join('\r\n');
    const name = table.name.replace(/[^\p{L}\p{M}\p{N}_ -]/gu, '').slice(0, 60).trim() || 'table';
    let filename = `${name}.csv`;
    for (let suffix = 2; used.has(filename.toLowerCase()); suffix++) filename = `${name}-${suffix}.csv`;
    used.add(filename.toLowerCase());
    return new File([text], filename, { type: 'text/csv' });
  });
}

export function parseClipboardTable(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = [], cell = '', quoted = false;
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (char === '"' && (quoted || !cell)) {
      if (quoted && text[index + 1] === '"') { cell += '"'; index++; } else quoted = !quoted;
    } else if (!quoted && char === '\t') { row.push(cell); cell = ''; }
    else if (!quoted && (char === '\n' || char === '\r')) {
      if (char === '\r' && text[index + 1] === '\n') index++;
      row.push(cell); rows.push(row); row = []; cell = '';
    } else cell += char;
  }
  if (quoted) throw new Error('Clipboard text contains an unfinished quoted cell');
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

export function nextColumnName(columns: string[]): string {
  let index = columns.length + 1;
  const existing = new Set(columns.map(column => column.toLowerCase()));
  while (existing.has(`column ${index}`)) index++;
  return `Column ${index}`;
}

export function pasteTableCells(table: TableDraft, rowIndex: number, columnIndex: number, matrix: string[][]): TableDraft {
  const width = Math.max(table.columns.length, columnIndex + Math.max(0, ...matrix.map(row => row.length)));
  const height = Math.max(table.rows.length, rowIndex + matrix.length);
  if (width > TABLE_LIMITS.columns || height > TABLE_LIMITS.rows || width * height > TABLE_LIMITS.cells) throw new Error('Pasted data exceeds the table limits');
  const columns = [...table.columns];
  while (columns.length < width) columns.push(nextColumnName(columns));
  const rows = Array.from({ length: height }, (_, row) => Array.from({ length: width }, (_, col) => table.rows[row]?.[col] ?? ''));
  matrix.forEach((row, r) => row.forEach((value, c) => { rows[rowIndex + r][columnIndex + c] = value; }));
  return { ...table, columns, rows };
}
