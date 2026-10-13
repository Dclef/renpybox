export type MarkdownBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'list'; ordered: boolean; items: { depth: number; text: string }[] }
  | { type: 'code'; text: string }
  | { type: 'quote'; text: string }
  | { type: 'rule' }
  | { type: 'paragraph'; text: string };

export type InlinePart = { type: 'text' | 'code' | 'strong' | 'link'; text: string; href?: string };
export type FormattedBlock = MarkdownBlock & { inline?: InlinePart[]; itemInline?: InlinePart[][] };
export interface ChangelogResult { pages: FormattedBlock[][]; truncated: boolean }

/** Release-author notes are not part of the displayed changelog, including a truncated comment. */
export function stripChangelogComments(source: string): string {
  return source.replace(/<!--[\s\S]*?(?:-->|$)/g, '');
}

/** Parsing and tokenization run only in the changelog worker. */
export function formatChangelog(source: string): ChangelogResult {
  const limit = 256_000;
  const blocks: FormattedBlock[] = parseMarkdown(source.slice(0, limit));
  const pages: FormattedBlock[][] = [[]];
  let cost = 0;
  function append(block: FormattedBlock, weight: number) {
    if (cost + weight > 80 && pages[pages.length - 1].length) {
      pages.push([]);
      cost = 0;
    }
    pages[pages.length - 1].push(block);
    cost += weight;
  }
  for (const block of blocks) {
    if (block.type === 'list') {
      for (let index = 0; index < block.items.length; index += 40) {
        const items = block.items.slice(index, index + 40);
        append({ ...block, items, itemInline: items.map(item => tokenizeInline(item.text)) }, items.length);
      }
    } else {
      if ('text' in block && block.type !== 'code') block.inline = tokenizeInline(block.text);
      append(block, 1);
    }
  }
  return { pages, truncated: source.length > limit };
}

function tokenizeInline(text: string): InlinePart[] {
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>()]+)/g;
  const parts: InlinePart[] = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) parts.push({ type: 'text', text: text.slice(cursor, start) });
    if (match[1] !== undefined) parts.push({ type: 'code', text: match[1] });
    else if (match[2] !== undefined) parts.push({ type: 'strong', text: match[2] });
    else {
      const href = match[4] ?? match[5];
      parts.push({ type: /^https?:\/\//i.test(href) ? 'link' : 'text', text: match[3] ?? match[5], href });
    }
    cursor = start + match[0].length;
  }
  if (cursor < text.length) parts.push({ type: 'text', text: text.slice(cursor) });
  return parts;
}

/** GitHub 发布说明可能是 HTML：只做文本替换降级为 Markdown，不解析、不插入任何 HTML。 */
function htmlToMarkdown(source: string): string {
  source = stripChangelogComments(source);
  if (!/<\/?(?:h[1-6]|p|ul|ol|li|br|code|pre|a|strong|div)\b/i.test(source)) return source;
  return source
    .replace(/<h([1-6])[^>]*>/gi, (_, level: string) => `\n${'#'.repeat(Number(level))} `)
    .replace(/<li[^>]*>/gi, '\n- ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(?:h[1-6]|p|div|ul|ol|li|pre)>/gi, '\n')
    .replace(/<\/?code[^>]*>/gi, '`')
    .replace(/<\/?(?:strong|b)>/gi, '**')
    .replace(/<a\s[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)')
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&');
}

/** 按行切分 Markdown 块：标题、列表、围栏代码、引用、分隔线，其余合并为段落。 */
export function parseMarkdown(source: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = htmlToMarkdown(source).replace(/\r\n?/g, '\n').split('\n');
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
    paragraph = [];
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const last = blocks[blocks.length - 1];
    const fence = /^\s*(```|~~~)/.exec(line);
    if (fence) {
      flush();
      const code: string[] = [];
      for (index += 1; index < lines.length && !lines[index].trim().startsWith(fence[1]); index += 1) code.push(lines[index]);
      blocks.push({ type: 'code', text: code.join('\n') });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    const heading = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (heading) {
      flush();
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      continue;
    }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) {
      flush();
      blocks.push({ type: 'rule' });
      continue;
    }
    const item = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      flush();
      const ordered = /\d/.test(item[2]);
      const entry = { depth: Math.min(3, Math.floor(item[1].replace(/\t/g, '  ').length / 2)), text: item[3] };
      // 缩进子项并入当前列表，靠 data-depth 缩进显示
      if (last?.type === 'list' && (last.ordered === ordered || entry.depth > 0)) last.items.push(entry);
      else blocks.push({ type: 'list', ordered, items: [entry] });
      continue;
    }
    const quote = /^\s*>\s?(.*)$/.exec(line);
    if (quote) {
      flush();
      if (last?.type === 'quote') last.text += ` ${quote[1]}`;
      else blocks.push({ type: 'quote', text: quote[1] });
      continue;
    }
    // 列表项的缩进续行归入上一项，而不是另起段落
    if (!paragraph.length && last?.type === 'list' && /^\s+\S/.test(line)) {
      last.items[last.items.length - 1].text += ` ${line.trim()}`;
      continue;
    }
    paragraph.push(line.trim());
  }
  flush();
  return blocks;
}
