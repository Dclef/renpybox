/**
 * 剧情蓝图右栏：一个 label 的逐行台词与真实译文。
 *
 * 数据来自 `/api/story-blueprint/label`：译文就是应用翻译缓存里的那一份，和校对台
 * 看到的一致；没有译文的行明确标「未译」，不再用 tl 文件里的英文占位冒充进度。
 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Spin, Tag } from 'antd';

import { ApiError, blueprintAssetUrl, getStoryBlueprintLabel } from '../../api';
import { useT } from '../../i18n';
import type {
  StoryBlueprintEdge,
  StoryBlueprintLabelDetail,
  StoryBlueprintNode,
  StoryBlueprintStatus,
} from '../../types';
import { formatPercent, isShowImage, labelName, nodeHeading } from './storyBlueprintView.mjs';

interface Props {
  node: StoryBlueprintNode;
  nodes: StoryBlueprintNode[];
  edges: StoryBlueprintEdge[];
  onClose: () => void;
  onOpen: (id: string) => void;
}

const STATUS_KEY: Record<StoryBlueprintStatus, 'story_blueprint_status_done' | 'story_blueprint_status_part' | 'story_blueprint_status_todo'> = {
  done: 'story_blueprint_status_done',
  part: 'story_blueprint_status_part',
  todo: 'story_blueprint_status_todo',
};

const STATUS_COLOR: Record<StoryBlueprintStatus, string> = {
  done: 'success',
  part: 'warning',
  todo: 'default',
};

export function LabelDetailPanel(props: Props) {
  const { node, nodes, edges, onClose, onOpen } = props;
  const t = useT();
  const [detail, setDetail] = useState<StoryBlueprintLabelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(0);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    setDetail(null);
    setCopied(0);
    setShowAll(false);
    getStoryBlueprintLabel(node.chapter, node.id)
      .then((data) => {
        if (alive) setDetail(data);
      })
      .catch((cause) => {
        if (!alive) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [node.chapter, node.id]);

  const heading = nodeHeading(node);
  const title = heading.title;
  const titles = useMemo(
    () => new Map(nodes.map((item) => [item.id, nodeHeading(item).title])),
    [nodes],
  );
  const outs = dedupe(
    edges
      .filter((edge) => edge.from === node.id)
      .map((edge) => ({
        key: `${edge.to}|${edge.option_src ?? ''}`,
        to: edge.to,
        label: edge.option_zh || edge.option_src || titles.get(edge.to) || edge.to,
        kind: edge.kind,
      })),
  );
  const ins = dedupe(
    edges
      .filter((edge) => edge.to === node.id)
      .map((edge) => ({
        key: `${edge.from}|${edge.option_src ?? ''}`,
        to: edge.from,
        label: titles.get(edge.from) || edge.from,
        kind: edge.kind,
      })),
  );
  const percent = node.say > 0 ? Math.min(100, (node.progress / node.say) * 100) : 0;
  const lines = detail?.lines ?? [];
  const pending = lines.filter((line) => !line.dst);
  const visibleLines = showAll ? lines : lines.slice(0, 40);

  const copyLine = async (line: { src: string; line: number }) => {
    try {
      await navigator.clipboard.writeText(line.src);
      setCopied(line.line);
      window.setTimeout(() => setCopied((current) => (current === line.line ? 0 : current)), 1200);
    } catch {
      setCopied(0);
    }
  };

  return (
    <aside className="rb-blueprint-drawer" role="dialog" aria-label={title}>
      <header className="rb-blueprint-drawer-head">
        <div>
          <p className="rb-blueprint-drawer-kicker">{t('story_blueprint_drawer_kicker')}</p>
          <h2 title={title}>{title}</h2>
          <span className="rb-blueprint-drawer-meta" title={`${node.file}:${node.line}–${node.end_line}`}>
            {t('story_blueprint_drawer_where')
              .replace('{chapter}', node.chapter)
              .replace('{line}', String(node.line))}
          </span>
        </div>
        <Button size="small" onClick={onClose}>
          {t('story_blueprint_drawer_close')}
        </Button>
      </header>

      <div className="rb-blueprint-drawer-summary">
        <Tag color={STATUS_COLOR[node.status]}>{t(STATUS_KEY[node.status])}</Tag>
        {t('story_blueprint_drawer_summary')
          .replace('{say}', String(node.say))
          .replace('{done}', String(node.progress))
          .replace('{percent}', formatPercent(node.progress, node.say))}
      </div>

      <div className="rb-blueprint-drawer-bar" aria-hidden>
        <span data-status={node.status} style={{ width: `${percent}%` }} />
      </div>

      {node.image ? (
        <div className="rb-blueprint-drawer-media">
          <img
            className="rb-blueprint-drawer-image"
            src={blueprintAssetUrl(node.image.path)}
            alt=""
            loading="lazy"
            decoding="async"
          />
          {isShowImage(node.image) ? (
            <span className="rb-blueprint-drawer-source" title={t('story_blueprint_show_source_hint')}>
              {t('story_blueprint_show_source')}
            </span>
          ) : null}
        </div>
      ) : (
        <div className="rb-blueprint-drawer-image is-empty">{t('story_blueprint_no_image')}</div>
      )}

      {node.placeholder ? (
        <p className="rb-blueprint-drawer-note">
          {t('story_blueprint_drawer_placeholder_note').replace('{blocks}', String(node.tl_blocks))}
        </p>
      ) : null}

      <section className="rb-blueprint-drawer-section">
        <h3>
          {t('story_blueprint_detail_lines')}
          <span className="rb-blueprint-drawer-count">
            {detail ? `${lines.length - pending.length}/${lines.length}` : ''}
          </span>
        </h3>
        <p className="rb-blueprint-drawer-tip">{t('story_blueprint_detail_tip')}</p>
        {loading ? (
          <div className="rb-blueprint-drawer-empty">
            <Spin size="small" /> {t('story_blueprint_detail_loading')}
          </div>
        ) : error ? (
          <p className="rb-blueprint-drawer-empty">{t('story_blueprint_detail_failed').replace('{error}', error)}</p>
        ) : lines.length === 0 ? (
          <p className="rb-blueprint-drawer-empty">{t('story_blueprint_drawer_none')}</p>
        ) : (
          <>
            <ol className="rb-blueprint-lines">
              {visibleLines.map((line) => (
                <li key={`${line.line}-${line.src}`} className="rb-blueprint-line" data-done={line.dst ? 'yes' : undefined}>
                  <span className="rb-blueprint-line-no">{line.line}</span>
                  <span className="rb-blueprint-line-body">
                    <span className="rb-blueprint-line-src">
                      {line.speaker ? <b>{line.speaker}：</b> : null}
                      {line.src}
                    </span>
                    {line.dst ? (
                      <span className="rb-blueprint-line-dst">{line.dst}</span>
                    ) : (
                      <span className="rb-blueprint-line-missing">{t('story_blueprint_detail_untranslated')}</span>
                    )}
                  </span>
                  <button
                    type="button"
                    className="rb-blueprint-line-copy"
                    onClick={() => void copyLine(line)}
                    title={t('story_blueprint_detail_copy')}
                  >
                    {copied === line.line ? t('story_blueprint_detail_copied') : t('story_blueprint_detail_copy')}
                  </button>
                </li>
              ))}
            </ol>
            {lines.length > 40 ? (
              <Button size="small" type="link" onClick={() => setShowAll((value) => !value)}>
                {showAll ? t('story_blueprint_detail_less') : t('story_blueprint_detail_more')}
              </Button>
            ) : null}
          </>
        )}
      </section>

      <section className="rb-blueprint-drawer-section">
        <h3>{t('story_blueprint_drawer_outs')}</h3>
        <p className="rb-blueprint-drawer-tip">{t('story_blueprint_drawer_outs_tip')}</p>
        {outs.length === 0 ? (
          <p className="rb-blueprint-drawer-empty">{t('story_blueprint_drawer_none')}</p>
        ) : (
          <ul>
            {outs.map((item) => (
              <li key={item.key}>
                <button type="button" className="rb-blueprint-link" onClick={() => onOpen(item.to)}>
                  <span className="rb-blueprint-link-label">{item.label}</span>
                  <span className="rb-blueprint-link-target">{labelName(item.to)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rb-blueprint-drawer-section">
        <h3>{t('story_blueprint_drawer_ins')}</h3>
        <p className="rb-blueprint-drawer-tip">{t('story_blueprint_drawer_ins_tip')}</p>
        {ins.length === 0 ? (
          <p className="rb-blueprint-drawer-empty">{t('story_blueprint_drawer_none')}</p>
        ) : (
          <ul>
            {ins.map((item) => (
              <li key={item.key}>
                <button type="button" className="rb-blueprint-link" onClick={() => onOpen(item.to)}>
                  <span className="rb-blueprint-link-label">{item.label}</span>
                  <span className="rb-blueprint-link-target">{labelName(item.to)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}

function dedupe<T extends { key: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.key)) return false;
    seen.add(item.key);
    return true;
  });
}
