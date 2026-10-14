/** 工具箱：保留 Qt5 工具注册与入口，提供分类筛选和清晰的项目依赖提示。 */
import { useMemo, useState } from 'react';
import { Button, Input } from 'antd';
import { ChevronRight, FolderOpen, Search } from 'lucide-react';
import { useT } from '../i18n';
import { searchTools, TOOL_ICONS, toolsByGroup, type ToolGroup, type ToolSpec } from '../tools';
import { localizeTool, TOOLBOX_COPY } from '../toolboxCopy';
import type { AppState } from '../useAppState';
import type { PageKey } from '../nav';
import { Banner, Dialog, Empty, PageHeader } from '../ui';

const TOOL_PAGES: Record<string, PageKey> = {
  local_glossary: 'glossary', text_preserve: 'preserve', honorific_placeholder: 'honorific',
  proofreading: 'proofreading', continue_translation: 'translation',
  one_key_translate: 'onekey', apply_translation: 'onekey-apply', pack_unpack: 'pack-unpack',
  ma_suite: 'ma-suite', batch_correction: 'batch-correction', name_extraction: 'name-extraction',
  direct_rpy_translate: 'direct-rpy-translate', source_translate: 'source-translate',
  hook_translate: 'hook-translate', hook_supplement: 'hook-supplement',
  font_replace: 'font-replace', rpy_extraction_settings: 'rpy-extraction',
  extract_to_tl: 'extract-to-tl', extract_json: 'extract-json',
  add_language: 'add-language', set_default_language: 'set-default-language',
  error_repair: 'error-repair', translation_reuse: 'translation-reuse',
  formatter: 'formatter', android_build: 'android-build',
  html_import: 'html-import', game_mod: 'game-mod',
};

type ToolboxCopy = typeof TOOLBOX_COPY.ZH;
function ToolCard({ tool, blocked, active, onOpen, copy }: {
  tool: ToolSpec; blocked: boolean; active: boolean;
  onOpen: (tool: ToolSpec) => void; copy: ToolboxCopy;
}) {
  const t = useT();
  const pending = !TOOL_PAGES[tool.key];
  return (
    <button
      type="button" className="tool-card" data-active={active} data-tool-key={tool.key}
      disabled={blocked} onClick={() => onOpen(tool)}
      title={`${blocked ? copy.projectRequired : copy.open(tool.title)}\n${tool.description}`}
    >
      <div className="tool-card-head">
        <div className="tool-card-head-left">
          <div className="tool-card-icon-container" aria-hidden="true">
            <span className="tool-card-icon" dangerouslySetInnerHTML={{ __html: TOOL_ICONS[tool.icon] }} />
          </div>
          <span className="rb-tool-title">{tool.title}</span>
        </div>
        {tool.step > 0 ? <span className="rb-tool-step" aria-hidden="true">{tool.step}</span> : null}
        <span className="tool-card-action" aria-hidden="true"><ChevronRight size={16} strokeWidth={1.75} /></span>
      </div>
      <div className="tool-card-body"><span className="rb-tool-desc">{tool.description}</span></div>
      {pending || blocked ? <div className="tool-card-footer">
        {pending ? <span className="rb-tool-availability">{t('tool_pending')}</span> : null}
        {blocked ? <span className="rb-tool-requirement">{copy.projectRequired}</span> : null}
      </div> : null}
    </button>
  );
}

export function ToolBoxPage({ state, onNavigate }: { state: AppState; onNavigate: (page: PageKey) => void }) {
  const t = useT();
  const lang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const copy = TOOLBOX_COPY[lang];
  const [selected, setSelected] = useState<ToolSpec | null>(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<ToolGroup | 'all'>('all');
  const hasProject = Boolean(state.project?.renpy_project_path);
  const groups = useMemo(() => toolsByGroup().map(group => ({
    ...group, tools: group.tools.map(tool => localizeTool(tool, lang)),
  })), [lang]);
  const needle = query.trim().toLocaleLowerCase();
  const originalMatches = useMemo(() => new Set(searchTools(query).map(tool => tool.key)), [query]);
  const filteredGroups = groups.filter(group => category === 'all' || group.group === category)
    .map(group => ({ ...group, tools: group.tools.filter(tool => !needle || originalMatches.has(tool.key)
      || `${tool.title} ${tool.description}`.toLocaleLowerCase().includes(needle)) }));
  const matchCount = filteredGroups.reduce((count, group) => count + group.tools.length, 0);
  const openTool = (tool: ToolSpec) => {
    const page = TOOL_PAGES[tool.key];
    if (page) onNavigate(page);
    else setSelected(tool);
  };
  const card = (tool: ToolSpec) => <ToolCard key={tool.key} tool={tool}
    blocked={tool.requiresProject && !hasProject} active={selected?.key === tool.key} onOpen={openTool} copy={copy} />;

  return (
    <div className="rb-page rb-toolbox">
      <PageHeader title={copy.title} description={copy.description} actions={(
        <Input prefix={<Search size={16} strokeWidth={1.75} />} className="toolbox-search"
          aria-label={copy.search} placeholder={copy.search} allowClear value={query}
          onChange={event => setQuery(event.target.value)} />
      )} />
      <nav className="rb-toolbox-categories" aria-label={copy.categories}>
        <button type="button" aria-pressed={category === 'all'} onClick={() => setCategory('all')}>{copy.all}</button>
        {groups.map(group => <button key={group.group} type="button" data-tool-group={group.group}
          aria-pressed={category === group.group} onClick={() => setCategory(group.group)}>
          {copy.groups[group.group][0]}<span>{group.tools.length}</span>
        </button>)}
      </nav>
      <div className="rb-toolbox-scroll">
        {!hasProject ? <Banner tone="info"><div className="rb-toolbox-project-hint">
          <span>{copy.unbound}</span>
          <Button size="small" icon={<FolderOpen size={14} />} onClick={() => onNavigate('project')}>{copy.selectProject}</Button>
        </div></Banner> : null}
        {needle ? <section className="tool-group">
          <div className="tool-group-header"><span className="tool-group-title">{copy.results}</span>
            <span className="tool-group-count" role="status">{copy.count(matchCount)}</span></div>
          {matchCount ? <div className="rb-tool-list">{filteredGroups.flatMap(group => group.tools).map(card)}</div>
            : <Empty><div className="rb-toolbox-empty"><span>{copy.empty}</span>
              <Button onClick={() => { setQuery(''); setCategory('all'); }}>{copy.reset}</Button></div></Empty>}
        </section> : filteredGroups.filter(group => group.tools.length).map(group => (
          <section className="tool-group" key={group.group}>
            <div className="tool-group-header"><div className="rb-toolbox-group-copy">
              <h2 className="tool-group-title">{copy.groups[group.group][0]}</h2>
              <p>{copy.groups[group.group][1]}</p>
            </div><span className="tool-group-count">{copy.count(group.tools.length)}</span></div>
            <div className="rb-tool-list">{group.tools.map(card)}</div>
          </section>
        ))}
      </div>
      {selected ? <Dialog title={selected.title} cancelText={lang === 'EN' ? 'Close' : '关闭'} onCancel={() => setSelected(null)}>
        <p>{selected.description}</p><Banner tone="info">{t('tool_pending')}</Banner>
      </Dialog> : null}
    </div>
  );
}
