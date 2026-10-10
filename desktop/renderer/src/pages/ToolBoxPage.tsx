/** 工具箱：沿用旧版四组分类与卡片入口，未接入工具明确提示使用原桌面版。 */

import { useMemo, useState } from 'react';
import { useT, type TextKey } from '../i18n';
import { Button, Input } from 'antd';
import { ChevronRight, Search } from 'lucide-react';

import { findTool, searchTools, TOOL_ICONS, toolsByGroup, type ToolSpec } from '../tools';
import type { AppState } from '../useAppState';
import type { PageKey } from '../nav';
import { Banner, Dialog, Empty, PageHeader } from '../ui';

const TOOL_PAGES: Record<string, PageKey> = {
  local_glossary: 'glossary', text_preserve: 'preserve', honorific_placeholder: 'honorific',
  proofreading: 'proofreading', continue_translation: 'translation',
  one_key_translate: 'onekey', apply_translation: 'onekey-apply', pack_unpack: 'pack-unpack',
  ma_suite: 'ma-suite', batch_correction: 'batch-correction', name_extraction: 'name-extraction',
};

/** 把 Lucide SVG 源码塞进内联 SVG；颜色靠 currentColor 跟随主题。 */
function InlineSvg(props: { markup: string }) {
  return <span className="tool-card-icon" dangerouslySetInnerHTML={{ __html: props.markup }} />;
}

function ToolCard(props: { tool: ToolSpec; blocked: boolean; onOpen: (tool: ToolSpec) => void }) {
  const { tool, blocked, onOpen } = props;
  const t = useT();
  return (
    <button
      type="button"
      className="tool-card"
      disabled={blocked}
      onClick={() => onOpen(tool)}
      title={blocked ? '需先选择游戏目录' : `打开${tool.title}`}
    >
      {tool.step > 0 ? <span className="rb-tool-step">{tool.step}</span> : null}
      <InlineSvg markup={TOOL_ICONS[tool.icon]} />
      <span className="rb-tool-copy">
        <span className="rb-tool-title">{tool.title}</span>
        <span className="rb-tool-desc">{tool.description}</span>
        {!TOOL_PAGES[tool.key] && <span className="rb-tool-availability">{t('tool_pending')}</span>}
        {blocked ? <span className="rb-tool-desc">需先选择游戏目录</span> : null}
      </span>
      <ChevronRight size={16} strokeWidth={1.75} />
    </button>
  );
}

const FLOW_STEPS: { page: PageKey; tool: string; title: TextKey; desc: TextKey }[] = [
  { page: 'glossary', tool: 'local_glossary', title: 'app_glossary_page', desc: 'flow_step_glossary_desc' },
  { page: 'preserve', tool: 'text_preserve', title: 'app_text_preserve_page', desc: 'flow_step_preserve_desc' },
  { page: 'honorific', tool: 'honorific_placeholder', title: 'app_honorific_page', desc: 'flow_step_honorific_desc' },
  { page: 'onekey', tool: 'one_key_translate', title: 'app_onekey_page', desc: 'flow_step_onekey_desc' },
];

function FlowGuide(props: { hasProject: boolean; onNavigate: (page: PageKey) => void }) {
  const { hasProject, onNavigate } = props;
  const t = useT();
  return (
    <div className="rb-flow-guide">
      <div className="rb-flow-guide-head">
        <span className="rb-tool-title">{t('flow_guide_title')}</span>
        <span className="rb-tool-desc">{t('flow_guide_desc')}</span>
      </div>
      {hasProject ? null : <Banner tone="warning">{t('flow_guide_no_project')}</Banner>}
      <ol className="rb-flow-steps" aria-label={t('flow_guide_title')}>
        {FLOW_STEPS.map((step, index) => {
          const blocked = findTool(step.tool)?.requiresProject === true && !hasProject;
          const needsDir = step.page === 'onekey' && !hasProject;
          return (
            <li key={step.page}>
              <Button className="rb-flow-step" disabled={blocked} onClick={() => onNavigate(step.page)}>
                <span className="rb-flow-step-index">{index + 1}</span>
                <span className="rb-flow-step-copy">
                  <span className="rb-tool-title">{t(step.title)}</span>
                  <span className="rb-tool-desc" data-warning={needsDir || undefined}>{t(needsDir ? 'flow_step_onekey_needs_dir' : step.desc)}</span>
                </span>
              </Button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function ToolBoxPage(props: { state: AppState; onNavigate: (page: PageKey) => void }) {
  const { state, onNavigate } = props;
  const [selected, setSelected] = useState<ToolSpec | null>(null);
  const [query, setQuery] = useState('');

  const openTool = (tool: ToolSpec) => {
    const page = TOOL_PAGES[tool.key];
    if (page) { onNavigate(page); return; }
    setSelected(tool);
  };
  const hasProject = Boolean(state.project?.renpy_project_path);
  const groups = useMemo(() => toolsByGroup(), []);
  const searching = query.trim().length > 0;
  const matches = useMemo(() => (searching ? searchTools(query) : null), [query, searching]);

  return (
    <div className="rb-page rb-toolbox">
      <PageHeader
        title="Ren'Py 工具箱"
        description="集中管理翻译流程、文本处理、术语资产与工程辅助工具"
        actions={(
          <Input
            style={{ width: 240, maxWidth: '100%' }}
            prefix={<Search size={16} strokeWidth={1.75} />}
            className="toolbox-search"
            aria-label="搜索工具"
            placeholder="搜索工具"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        )}
      />

      <div className="rb-toolbox-scroll">
        {hasProject ? null : (
          <Banner tone="warning">尚未绑定工程。需要项目的工具暂时不可用，请先到项目设置选择带 game/ 的目录。</Banner>
        )}

        {searching && matches ? (
          <section className="tool-group">
            <div className="tool-group-header">
              <span className="tool-group-title">搜索结果</span>
              <span className="tool-group-count">{matches.length} 款工具</span>
            </div>
            {matches.length === 0 ? (
              <Empty>没有匹配的工具</Empty>
            ) : (
              <div className="rb-tool-list">
                {matches.map((tool) => (
                  <ToolCard
                    key={tool.key}
                    tool={tool}
                    blocked={tool.requiresProject && !hasProject}
                    onOpen={openTool}
                  />
                ))}
              </div>
            )}
          </section>
        ) : null}

        {!searching ? groups.map((group) => {
          const tools = searching && matches ? group.tools.filter((tool) => matches.includes(tool)) : group.tools;
          if (tools.length === 0) return null;
          return (
            <section className="tool-group" key={group.group}>
              <div className="tool-group-header">
                <span className="tool-group-title">{group.title}</span>
                <span className="tool-group-count">{tools.length} 款工具</span>
              </div>
              {group.group === 'flow' ? <FlowGuide hasProject={hasProject} onNavigate={onNavigate} /> : null}
              <div className="rb-tool-list">
                {tools.map((tool) => (
                  <ToolCard
                    key={tool.key}
                    tool={tool}
                    blocked={tool.requiresProject && !hasProject}
                    onOpen={openTool}
                  />
                ))}
              </div>
            </section>
          );
        }) : null}
      </div>

      {selected ? (
        <Dialog title={selected.title} cancelText="关闭" onCancel={() => setSelected(null)}>
          <p>{selected.description}</p>
          <p className="card-description">关键词：{selected.keywords.join('、')}</p>
          <Banner tone="info">
            此工具暂不可用，请在原桌面版中执行。当前页面仅展示工具说明和使用条件。
          </Banner>
        </Dialog>
      ) : null}
    </div>
  );
}
