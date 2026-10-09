/**
 * Ren'Py 工具箱 —— 对齐 frontend/RenpyToolbox/RenpyToolboxPage.py 与 widget/ItemCard.py 的实测几何。
 *
 * 实测（nav=256、页宽 1023）：
 *   头部：左侧文字块 639x33 @ (24,24)（TitleLabel 18px + CaptionLabel 12px），
 *         **右侧 SearchLineEdit 320x33 @ (679,24)**，placeholder = toolbox_search_tools
 *         —— 搜索框属于这一页，不在导航栏（导航栏没有搜索框）。
 *   滚动区 975x664 @ (24,73)。
 *   小节：节头 975x14 = 组名 StrongBodyLabel 14px + 计数 CaptionLabel 12px（右对齐）；
 *         卡片容器在其下 20px；卡行间距 12。
 *   卡片 ItemCard 316x132、3 列、列距 14：
 *         头部 286x30 @ (15,13) = 序号码 22x22（fpx 11）+ 图标 20x20（间距 9）
 *         + 标题 SubtitleLabel 14px + 右侧箭头 36x30
 *         说明两行截断（TwoLineElideLabel 口径）。
 */

import { useMemo, useState } from 'react';

import { IconChevronRight, IconSearch } from '../icons';
import { searchTools, TOOL_ICONS, toolsByGroup, type ToolSpec } from '../tools';
import type { AppState } from '../useAppState';
import type { PageKey } from '../nav';
import { Banner, Dialog, Empty } from '../ui';

/** 把 Lucide SVG 源码塞进内联 SVG；颜色靠 currentColor 跟随主题。 */
function InlineSvg(props: { markup: string }) {
  return <span className="tool-card-icon" dangerouslySetInnerHTML={{ __html: props.markup }} />;
}

function ToolCard(props: { tool: ToolSpec; blocked: boolean; onOpen: (tool: ToolSpec) => void }) {
  const { tool, blocked, onOpen } = props;
  return (
    <button
      type="button"
      className="tool-card"
      disabled={blocked}
      onClick={() => onOpen(tool)}
      title={blocked ? '需先选择游戏目录' : `打开${tool.title}`}
    >
      <span className="tool-card-head">
        {tool.step > 0 ? <span className="tool-card-step">{tool.step}</span> : null}
        <InlineSvg markup={TOOL_ICONS[tool.icon]} />
        <span className="tool-card-title">{tool.title}</span>
        <span className="tool-card-go">
          <IconChevronRight size={16} />
        </span>
      </span>
      <span className="tool-card-body">
        <span className="tool-card-description">{tool.description}</span>
        {blocked ? <span className="tool-card-requirement">需先选择游戏目录</span> : null}
      </span>
    </button>
  );
}

export function ToolBoxPage(props: { state: AppState; onNavigate: (page: PageKey) => void }) {
  const { state, onNavigate } = props;
  const [selected, setSelected] = useState<ToolSpec | null>(null);
  const [query, setQuery] = useState('');

  const openTool = (tool: ToolSpec) => {
    if (tool.key === 'local_glossary') { onNavigate('glossary'); return; }
    if (tool.key === 'text_preserve') { onNavigate('preserve'); return; }
    if (tool.key === 'honorific_placeholder') { onNavigate('honorific'); return; }
    if (tool.key === 'proofreading') { onNavigate('proofreading'); return; }
    if (tool.key === 'continue_translation') { onNavigate('translation'); return; }
    setSelected(tool);
  };
  const hasProject = Boolean(state.project?.renpy_project_path);
  const groups = useMemo(() => toolsByGroup(), []);
  const searching = query.trim().length > 0;
  const matches = useMemo(() => (searching ? searchTools(query) : null), [query, searching]);

  return (
    <div className="settings-layout">
      <header className="settings-header toolbox-header">
        <div className="toolbox-header-text">
          <h1 className="settings-title">Ren'Py 工具箱</h1>
          <p className="settings-subtitle">集中管理翻译流程、文本处理、术语资产与工程辅助工具</p>
        </div>
        <div className="toolbox-search-wrap">
          <span className="toolbox-search-icon">
            <IconSearch size={15} />
          </span>
          <input
            className="toolbox-search"
            type="text"
            aria-label="搜索工具"
            placeholder="搜索工具"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </header>

      <div className="settings-scroll">
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
              <div className="tool-grid">
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
              <div className="tool-grid">
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
