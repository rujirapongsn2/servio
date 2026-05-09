function normalizeInlineMarkdownTables(raw: string): string {
  const separatorPattern = /\|(?:\s*:?-{3,}:?\s*\|){2,}/g;
  let output = "";
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = separatorPattern.exec(raw)) !== null) {
    const separatorStart = match.index;
    const separatorEnd = separatorStart + match[0].length;
    const separatorPipeCount = (match[0].match(/\|/g) || []).length;

    const pipePositionsBeforeSeparator: number[] = [];
    for (let i = cursor; i < separatorStart; i += 1) {
      if (raw[i] === "|") pipePositionsBeforeSeparator.push(i);
    }

    if (pipePositionsBeforeSeparator.length < separatorPipeCount) {
      continue;
    }

    const headerStart =
      pipePositionsBeforeSeparator[pipePositionsBeforeSeparator.length - separatorPipeCount];
    const header = raw.slice(headerStart, separatorStart).trim();

    if (!header.startsWith("|") || !header.endsWith("|")) {
      continue;
    }

    const rows: string[] = [];
    let position = separatorEnd;

    while (position < raw.length) {
      while (raw[position] === " " || raw[position] === "\t") position += 1;
      if (raw[position] !== "|") break;

      let pipesSeen = 0;
      let rowEnd = position;

      while (rowEnd < raw.length && pipesSeen < separatorPipeCount) {
        if (raw[rowEnd] === "|") pipesSeen += 1;
        rowEnd += 1;
      }

      if (pipesSeen !== separatorPipeCount) break;

      rows.push(raw.slice(position, rowEnd).trim());
      position = rowEnd;
    }

    if (rows.length === 0) {
      continue;
    }

    output += raw.slice(cursor, headerStart).trimEnd();
    output += `\n\n${header}\n${match[0].trim()}\n${rows.join("\n")}\n\n`;
    cursor = position;
    separatorPattern.lastIndex = position;
  }

  return output + raw.slice(cursor);
}

export function normalizeMarkdownForChat(raw: string): string {
  if (!raw) return "";

  const unescaped = raw.replace(/\r\n/g, "\n").replace(/\\([#|])/g, "$1");
  let text = normalizeInlineMarkdownTables(unescaped).trim();

  // Headings sometimes arrive inline after a sentence or list item.
  text = text.replace(/([^\n])\s+\\?(#{1,6})\s+/g, "$1\n\n$2 ");

  // Turn inline numbered sequences into proper markdown list items.
  text = text.replace(/([^\n])\s+(\d+)\.\s+/g, "$1\n$2. ");

  // Turn inline bullets into proper markdown bullet lines.
  text = text.replace(/([^\n])\s+([*-])\s+/g, "$1\n$2 ");

  return text;
}
