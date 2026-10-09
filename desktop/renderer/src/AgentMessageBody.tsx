import type { ReactNode } from 'react';

function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>;
    return part;
  });
}

export function AgentMessageBody(props: { text: string }) {
  const lines = props.text.split('\n');
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const start = index;
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    if (line.trim().startsWith('```')) {
      const language = line.trim().slice(3);
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push(<pre key={start} aria-label={language ? `${language} 代码` : '代码'}><code>{code.join('\n')}</code></pre>);
      continue;
    }
    const heading = line.match(/^#{1,3}\s+(.+)/);
    if (heading) {
      blocks.push(<h3 key={start}>{inline(heading[1])}</h3>);
      index += 1;
      continue;
    }
    const list = /^\s*(?:[-*]|\d+\.)\s+/;
    if (list.test(line)) {
      const items: ReactNode[] = [];
      const ordered = /^\s*\d+\./.test(line);
      while (index < lines.length && list.test(lines[index])) {
        items.push(<li key={index}>{inline(lines[index].replace(list, ''))}</li>);
        index += 1;
      }
      blocks.push(ordered ? <ol key={start}>{items}</ol> : <ul key={start}>{items}</ul>);
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !/^\s*(?:```|#{1,3}\s|[-*]\s|\d+\.\s)/.test(lines[index])) {
      paragraph.push(lines[index]);
      index += 1;
    }
    if (!paragraph.length) { paragraph.push(lines[index]); index += 1; }
    blocks.push(<p key={start}>{inline(paragraph.join('\n'))}</p>);
  }
  return <div className="agent-message-body">{blocks}</div>;
}
