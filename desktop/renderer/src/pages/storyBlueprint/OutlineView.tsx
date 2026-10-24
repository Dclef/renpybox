/**
 * 剧情大纲：把一章的 label 排成可折叠树，分支以子行的形式挂在父 label 下面。
 *
 * 为什么不用画布：画布要靠缩放/拖拽把内容塞进视口，卡片一小就点不准、一拖就空白；
 * 而译者真正想知道的是「这一段之后去哪、哪条分支还没翻」。用树形列表表达同样
 * 的信息，全部操作退化成「滚动 + 点击」，不依赖指针精度。
 */
import { useMemo, useState } from 'react';
import { Tag, Tooltip } from 'antd';
import { ChevronDown, ChevronRight, CornerDownRight, GitBranch } from 'lucide-react';

import { useT } from '../../i18n';
import type {
  StoryBlueprintChapter,
  StoryBlueprintEdge,
  StoryBlueprintNode,
  StoryBlueprintStatus,
} from '../../types';
import { formatPercent, labelName, nodeHeading } from './storyBlueprintView.mjs';

interface Props {
  nodes: StoryBlueprintNode[];
  allNodes: StoryBlueprintNode[];
  edges: StoryBlueprintEdge[];
  chapters: StoryBlueprintChapter[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNavigate: (chapter: string, id: string) => void;
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

export function OutlineView(props: Props) {
  const { nodes, allNodes, edges, chapters, selectedId, onSelect, onNavigate } = props;
  const t = useT();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const byId = useMemo(() => new Map(allNodes.map((node) => [node.id, node])), [allNodes]);
  const chapterOf = useMemo(() => new Map(chapters.map((chapter) => [chapter.id, chapter])), [chapters]);

  // 出边按 label 分组：一个 label 的所有「去哪」都挂在它自己下面。
  const outs = useMemo(() => {
    const table = new Map<string, StoryBlueprintEdge[]>();
    for (const edge of edges) {
      const list = table.get(edge.from) ?? [];
      list.push(edge);
      table.set(edge.from, list);
    }
    return table;
  }, [edges]);

  const toggle = (id: string) => {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (nodes.length === 0) {
    return <div className="rb-blueprint-state">{t('story_blueprint_list_empty')}</div>;
  }

  return (
    <div className="rb-outline" role="tree">
      {nodes.map((node) => {
        const branches = outs.get(node.id) ?? [];
        const isOpen = branches.length > 0 && !collapsed.has(node.id);
        const heading = nodeHeading(node);
        const percent = node.say > 0 ? Math.min(100, (node.progress / node.say) * 100) : 0;
        return (
          <div key={node.id} className="rb-outline-item" role="treeitem" aria-expanded={isOpen}>
            <div
              className="rb-outline-row"
              data-status={node.status}
              data-active={node.id === selectedId || undefined}
            >
              <button
                type="button"
                className="rb-outline-toggle"
                aria-label={isOpen ? t('story_blueprint_outline_collapse') : t('story_blueprint_outline_expand')}
                disabled={branches.length === 0}
                onClick={() => toggle(node.id)}
              >
                {branches.length === 0 ? null : isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              <button type="button" className="rb-outline-main" onClick={() => onSelect(node.id)}>
                <span className="rb-outline-title">{heading.title}</span>
                {heading.subtitle ? (
                  <span className="rb-outline-src" lang="en">{heading.subtitle}</span>
                ) : null}
              </button>
              <span className="rb-outline-progress" aria-hidden>
                <span className="rb-outline-bar" data-status={node.status}>
                  <span style={{ width: `${percent}%` }} />
                </span>
                <span className="rb-outline-ratio">{node.progress}/{node.say}</span>
              </span>
              <Tag color={STATUS_COLOR[node.status]}>{t(STATUS_KEY[node.status])}</Tag>
              <span className="rb-outline-meta">{node.file}:{node.line}</span>
              {branches.length > 0 ? (
                <Tooltip title={t('story_blueprint_outline_branch_count').replace('{count}', String(branches.length))}>
                  <span className="rb-outline-badge">
                    <GitBranch size={11} />
                    {branches.length}
                  </span>
                </Tooltip>
              ) : null}
            </div>

            {isOpen ? (
              <ul className="rb-outline-branches" role="group">
                {branches.map((edge) => {
                  const target = byId.get(edge.to);
                  const chapter = target ? chapterOf.get(target.chapter) : undefined;
                  return (
                    <li key={`${edge.to}-${edge.option_src ?? ''}-${edge.line}`}>
                      <button
                        type="button"
                        className="rb-outline-branch"
                        onClick={() => (target ? onNavigate(target.chapter, target.id) : onSelect(node.id))}
                      >
                        <CornerDownRight size={12} className="rb-outline-branch-icon" />
                        <span className="rb-outline-branch-kind" data-kind={edge.kind}>
                          {edge.kind === 'menu'
                            ? t('story_blueprint_outline_option')
                            : t('story_blueprint_outline_jump')}
                        </span>
                        <span className="rb-outline-branch-label">
                          {labelOf(edge, target)}
                        </span>
                        <span className="rb-outline-branch-target">
                          {targetOf(edge, target, node, chapter)}
                        </span>
                        {target ? (
                          <span className="rb-outline-branch-progress">
                            {formatPercent(target.progress, target.say)}
                          </span>
                        ) : (
                          <Tag>{t('story_blueprint_outline_missing')}</Tag>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/** 分支左侧文字：有选项原文就用选项，否则用目标 label 的名字。 */
function labelOf(edge: StoryBlueprintEdge, target: StoryBlueprintNode | undefined): string {
  const option = edge.option_zh || edge.option_src;
  if (option) return option;
  return target ? nodeHeading(target).title : edge.to;
}

/**
 * 分支右侧「去向」：只在和左侧文字不重复时才显示，避免同一句话出现两遍
 * （很多 label 的首句就是它的选项文本，重复显示只会让这行更难读）。
 */
function targetOf(
  edge: StoryBlueprintEdge,
  target: StoryBlueprintNode | undefined,
  node: StoryBlueprintNode,
  chapter: StoryBlueprintChapter | undefined,
): string {
  if (!target) return edge.to;
  const title = nodeHeading(target).title;
  const label = labelOf(edge, target);
  const prefix = target.chapter !== node.chapter && chapter ? `[${chapter.id}] ` : '';
  if (title.trim() === label.trim()) return `${prefix}${labelName(target.id)}`;
  return `${prefix}${title}`;
}
