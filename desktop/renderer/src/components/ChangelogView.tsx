import { useEffect, useState } from 'react';
import { Alert, Pagination, Spin } from 'antd';
import { useT } from '../i18n';
import ChangelogWorker from '../changelog.worker?worker&inline';
import { stripChangelogComments, type ChangelogResult, type InlinePart } from '../changelogMarkdown';

function Inline({ parts }: { parts?: InlinePart[] }) {
  return <>{parts?.map((part, index) => {
    if (part.type === 'code') return <code key={index}>{part.text}</code>;
    if (part.type === 'strong') return <strong key={index}>{part.text}</strong>;
    if (part.type === 'link') return <a key={index} href={part.href} target="_blank" rel="noopener noreferrer">{part.text}</a>;
    return part.text;
  })}</>;
}

/** Worker isolation keeps malformed release notes from blocking window controls. */
export function ChangelogView({ markdown }: { markdown: string }) {
  const t = useT();
  const [result, setResult] = useState<ChangelogResult | null>(null);
  const [plain, setPlain] = useState(false);
  const [page, setPage] = useState(1);
  useEffect(() => {
    setResult(null);
    setPlain(false);
    setPage(1);
    let worker: Worker | undefined;
    let active = true;
    const fallback = () => { if (active) setPlain(true); worker?.terminate(); };
    const timer = window.setTimeout(fallback, 3000);
    try {
      worker = new ChangelogWorker();
      worker.onmessage = (event: MessageEvent<ChangelogResult>) => {
        if (active) setResult(event.data);
        window.clearTimeout(timer);
        worker?.terminate();
      };
      worker.onerror = (event) => { event.preventDefault(); window.clearTimeout(timer); fallback(); };
      worker.postMessage(markdown);
    } catch {
      window.clearTimeout(timer);
      fallback();
    }
    return () => { active = false; window.clearTimeout(timer); worker?.terminate(); };
  }, [markdown]);

  if (plain) return <div className="update-changelog">
    <Alert type="info" title={t('changelog_plain_fallback')} />
    <pre style={{ whiteSpace: 'pre-wrap' }}>{stripChangelogComments(markdown.slice(0, 256_000))}</pre>
  </div>;
  if (!result) return <Spin description={t('changelog_loading')}><div style={{ minHeight: 100 }} /></Spin>;
  return <>
    {result.truncated ? <Alert type="info" title={t('changelog_truncated')} /> : null}
    <div className="update-changelog" key={page}>
      {(result.pages[page - 1] ?? []).map((block, index) => {
        if (block.type === 'heading') {
          const Tag = `h${Math.min(6, block.level + 2)}` as 'h3';
          return <Tag key={index}><Inline parts={block.inline} /></Tag>;
        }
        if (block.type === 'list') {
          const List = block.ordered ? 'ol' : 'ul';
          return <List key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex} data-depth={item.depth}><Inline parts={block.itemInline?.[itemIndex]} /></li>)}</List>;
        }
        if (block.type === 'code') return <pre key={index}><code>{block.text}</code></pre>;
        if (block.type === 'quote') return <blockquote key={index}><Inline parts={block.inline} /></blockquote>;
        if (block.type === 'rule') return <hr key={index} />;
        return <p key={index}><Inline parts={block.inline} /></p>;
      })}
    </div>
    {result.pages.length > 1 ? <Pagination simple current={page} total={result.pages.length} pageSize={1} onChange={setPage} style={{ marginTop: 16 }} /> : null}
  </>;
}
