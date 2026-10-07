/** 项目资料工作台：手动编辑保存在项目资产仓库，提示词预览复用真实构造器。 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { request } from '../api';
import type { AppState } from '../useAppState';
import { Banner, Dialog, Empty, Switch } from '../ui';

interface CharacterCard {
  id: string;
  name: string;
  name_translation: string;
  aliases: string[];
  match_keywords: string[];
  identity: string;
  personality: string;
  speech_style: string;
  relationship_notes: string;
  prompt_notes: string;
  sample_lines: string[];
  enabled: boolean;
  is_primary: boolean;
}
interface EditableAssets {
  worldbook: Record<string, string>;
  characters: CharacterCard[];
  worldbook_enabled: boolean;
  characters_enabled: boolean;
}
interface WorkbenchSnapshot extends EditableAssets {
  storage_key: string;
  revision: number;
  worldbook_draft: Record<string, string>;
  character_drafts: CharacterCard[];
}
interface PromptPreview {
  matched_names: string[];
  world_context: string;
  character_context: string;
  context: string;
}

type TabKey = 'overview' | 'worldbook' | 'characters' | 'preview';
const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '概览' }, { key: 'worldbook', label: '世界观' },
  { key: 'characters', label: '角色卡' }, { key: 'preview', label: '提示词预览' },
];
const WORLD_FIELDS = [
  ['project_name', '项目名称'], ['genre', '作品类型'], ['setting_summary', '背景摘要'],
  ['tone_style', '整体语气'], ['era_background', '时代与环境'], ['narrative_rules', '叙事规则'],
  ['format_rules', '格式规则'], ['spoiler_notes', '剧透备注'], ['reference_notes', '补充参考'],
] as const;
const CHARACTER_FIELDS = [
  ['name', '角色名称'], ['name_translation', '推荐译名'], ['identity', '身份与经历'],
  ['personality', '性格'], ['speech_style', '说话风格'], ['prompt_notes', '翻译提示'],
  ['aliases', '别名'], ['match_keywords', '匹配关键词'], ['relationship_notes', '关系备注'],
  ['sample_lines', '台词示例'],
] as const;
const LIST_FIELDS = new Set(['aliases', 'match_keywords', 'sample_lines']);

function editable(snapshot: WorkbenchSnapshot): EditableAssets {
  // 扩展世界观字段由后端保留，表单只编辑原工作台公开的九个字段。
  return {
    worldbook: Object.fromEntries(WORLD_FIELDS.map(([key]) => [key, String(snapshot.worldbook[key] ?? '')])),
    characters: structuredClone(snapshot.characters),
    worldbook_enabled: snapshot.worldbook_enabled,
    characters_enabled: snapshot.characters_enabled,
  };
}
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

export function WorkbenchPage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void }) {
  const { state, onDirtyChange } = props;
  const [tab, setTab] = useState<TabKey>('overview');
  const [snapshot, setSnapshot] = useState<WorkbenchSnapshot | null>(null);
  const [draft, setDraft] = useState<EditableAssets | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<'delete' | 'reload' | 'apply' | null>(null);
  const [sample, setSample] = useState('');
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const sequence = useRef(0);
  const dirtyRef = useRef(false);
  const projectRef = useRef('');
  const projectKey = JSON.stringify([state.project?.renpy_project_path, state.project?.renpy_tl_folder,
    state.settings?.values.input_folder, state.settings?.values.output_folder]);
  projectRef.current = projectKey;
  const dirty = Boolean(snapshot && draft && JSON.stringify(editable(snapshot)) !== JSON.stringify(draft));
  dirtyRef.current = dirty;
  const hasDrafts = Boolean(snapshot && (Object.values(snapshot.worldbook_draft).some(Boolean) || snapshot.character_drafts.length));
  const selected = draft?.characters.find((card) => card.id === selectedId);
  const worldCount = draft ? Object.values(draft.worldbook).filter((text) => text.trim()).length : 0;

  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => { onDirtyChange?.(false); }, [onDirtyChange]);

  const adopt = useCallback((next: WorkbenchSnapshot) => {
    setSnapshot(next);
    setDraft(editable(next));
    setSelectedId((current) => next.characters.some((card) => card.id === current) ? current : next.characters[0]?.id ?? '');
    setPreview(null);
    setError('');
  }, []);

  const reload = useCallback(async () => {
    const current = ++sequence.current;
    const key = projectRef.current;
    setLoading(true);
    setError('');
    try {
      const next = await request<WorkbenchSnapshot>('/api/workbench');
      if (current === sequence.current && key === projectRef.current) adopt(next);
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally {
      if (current === sequence.current && key === projectRef.current) setLoading(false);
    }
  }, [adopt]);

  useEffect(() => {
    sequence.current += 1;
    setBusy(false);
    setLoading(false);
    setPreview(null);
    setConfirm(null);
    // 外部切换项目时保留手动编辑，用户可以先导出，再明确重新加载。
    if (dirtyRef.current) {
      setError('项目已变更，请先导出未保存的资料，再重新加载当前项目。');
    } else {
      setSnapshot(null);
      setDraft(null);
      void reload();
    }
    return () => { sequence.current += 1; };
  }, [reload, projectKey]);

  async function save() {
    if (!snapshot || !draft || busy) return;
    if (draft.characters.some((card) => !card.name.trim())) {
      setError('请填写每张角色卡的名称后再保存。');
      return;
    }
    const current = ++sequence.current;
    const key = projectRef.current;
    setBusy(true);
    setError('');
    try {
      const next = await request<WorkbenchSnapshot>('/api/workbench', {
        method: 'PATCH', body: JSON.stringify({ storage_key: snapshot.storage_key, revision: snapshot.revision, ...draft }),
      });
      if (current === sequence.current && key === projectRef.current) {
        adopt(next);
        state.pushToast('success', '项目资料已保存');
      }
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally { if (current === sequence.current && key === projectRef.current) setBusy(false); }
  }

  async function applyDrafts() {
    setConfirm(null);
    if (!snapshot || busy || dirty) return;
    const current = ++sequence.current;
    const key = projectRef.current;
    setBusy(true);
    setError('');
    try {
      const next = await request<WorkbenchSnapshot>('/api/workbench/apply-drafts', {
        method: 'POST', body: JSON.stringify({ storage_key: snapshot.storage_key, revision: snapshot.revision }),
      });
      if (current === sequence.current && key === projectRef.current) {
        adopt(next);
        state.pushToast('success', '草稿已应用到正式项目资料');
      }
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally { if (current === sequence.current && key === projectRef.current) setBusy(false); }
  }

  async function previewPrompt() {
    if (!snapshot || dirty || busy) return;
    const current = ++sequence.current;
    const key = projectRef.current;
    setBusy(true);
    setError('');
    try {
      const next = await request<PromptPreview>('/api/workbench/preview', {
        method: 'POST', body: JSON.stringify({ storage_key: snapshot.storage_key, revision: snapshot.revision, sample }),
      });
      if (current === sequence.current && key === projectRef.current) setPreview(next);
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally { if (current === sequence.current && key === projectRef.current) setBusy(false); }
  }

  function addCharacter() {
    if (!draft) return;
    const id = `character_${crypto.randomUUID()}`;
    const name = `新角色 ${draft.characters.length + 1}`;
    const card: CharacterCard = {
      id, name, name_translation: '', aliases: [], match_keywords: [name], identity: '',
      personality: '', speech_style: '', relationship_notes: '', prompt_notes: '', sample_lines: [],
      enabled: true, is_primary: false,
    };
    setDraft({ ...draft, characters: [...draft.characters, card] });
    setSelectedId(id);
    setSearch('');
    setTab('characters');
    setPreview(null);
  }

  function updateCharacter(key: keyof CharacterCard, value: unknown) {
    if (!draft || !selected) return;
    setDraft({ ...draft, characters: draft.characters.map((card) => card.id === selected.id ? { ...card, [key]: value } : card) });
    setPreview(null);
  }

  function exportAssets() {
    if (!snapshot || !draft) return;
    const data = {
      schema_version: 1, worldbook: { ...snapshot.worldbook, ...draft.worldbook }, character_cards: draft.characters,
      worldbook_draft: snapshot.worldbook_draft, character_drafts: snapshot.character_drafts,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'RenpyBox_Workbench.json';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="workbench-workspace">
      <header className="workbench-header">
        <div className="workbench-header-text">
          <h1 className="workbench-title">角色与世界观</h1>
          <p className="workbench-subtitle">维护当前项目的背景、角色资料与翻译上下文</p>
        </div>
        <div className="workbench-header-actions">
          <button className="btn" disabled={!draft || busy || loading} onClick={exportAssets}>导出资料</button>
          <button className="btn" disabled={!hasDrafts || dirty || busy || loading} title={dirty ? '先保存手动编辑，再应用草稿' : undefined} onClick={() => setConfirm('apply')}>应用草稿</button>
          <button className="btn btn-primary" disabled={!dirty || busy || loading} onClick={() => void save()}>{busy ? '处理中…' : '保存修改'}</button>
        </div>
      </header>
      <div className="workbench-tabs" role="tablist" aria-label="工作台分页">
        {TABS.map((item) => <button key={item.key} role="tab" aria-selected={tab === item.key} className="quiet-pill" onClick={() => setTab(item.key)}>{item.label}</button>)}
      </div>
      <div className="workbench-status">
        <span className="workbench-status-title">{loading ? '正在读取项目资料…' : dirty ? '有未保存的修改' : snapshot ? '项目资料已同步' : '等待选择项目'}</span>
        <span className="workbench-status-hint">{draft ? `世界观 ${worldCount} 项 · 角色 ${draft.characters.length} 位${dirty ? ' · 点击保存后用于后续翻译' : ''}` : '选择项目后，即可维护独立的背景与角色资料。'}</span>
      </div>
      {error && <Banner tone="error">{error} <button className="btn" disabled={busy || loading} onClick={() => dirty ? setConfirm('reload') : void reload()}>重新加载</button></Banner>}
      <div className="workbench-body">
        {!draft ? <div className="workbench-panel"><Empty>{loading ? '正在加载…' : '项目资料暂不可用，请检查项目设置。'}</Empty></div> : tab === 'overview' ? (
          <div className="workbench-panel">
            <div className="workbench-summary">
              <div className="workbench-summary-copy"><span className="workbench-eyebrow">项目背景</span><h2>{draft.worldbook.project_name || '项目背景尚未填写'}</h2><p>{draft.worldbook.setting_summary || '填写背景、语气与人物关系，保存后用于下一次翻译。'}</p><button className="btn" onClick={() => setTab('worldbook')}>完善世界观</button></div>
              <div className="workbench-overview-stats"><div><strong>{worldCount}</strong><span>背景设定</span></div><div><strong>{draft.characters.length}</strong><span>角色资料</span></div><div><strong>{snapshot?.character_drafts.length ?? 0}</strong><span>待审核角色</span></div></div>
            </div>
            <div className="workbench-card">
              <div className="workbench-card-title">翻译上下文</div>
              <div className="workbench-card-hint">世界观作为全局背景；角色卡根据原文中的名称、别名和关键词按需匹配。</div>
              <div className="workbench-switch-row"><span>注入世界观</span><Switch checked={draft.worldbook_enabled} disabled={busy} label="注入世界观" onChange={(value) => { setDraft({ ...draft, worldbook_enabled: value }); setPreview(null); }} /></div>
              <div className="workbench-switch-row"><span>注入角色卡</span><Switch checked={draft.characters_enabled} disabled={busy} label="注入角色卡" onChange={(value) => { setDraft({ ...draft, characters_enabled: value }); setPreview(null); }} /></div>
            </div>
            {hasDrafts && <div className="workbench-card"><div className="workbench-card-title">已有资料草稿</div><p className="workbench-card-hint">世界观草稿 {Object.values(snapshot?.worldbook_draft ?? {}).filter(Boolean).length} 项 · 角色草稿 {snapshot?.character_drafts.length ?? 0} 张。可先查看内容，再应用到正式资料。</p><details><summary>查看草稿</summary><pre className="workbench-preview-text">{JSON.stringify({ 世界观: snapshot?.worldbook_draft, 角色: snapshot?.character_drafts }, null, 2)}</pre></details></div>}
          </div>
        ) : tab === 'worldbook' ? (
          <div className="workbench-panel">
            <div className="workbench-card"><div className="workbench-card-title">故事背景与翻译约定</div><div className="workbench-card-hint">内容保存在当前项目中。无需填写所有字段，优先记录背景摘要与整体语气。</div>
              <div className="workbench-form-grid">{WORLD_FIELDS.map(([key, label], index) => <label className={`workbench-field ${index > 1 ? 'workbench-field-wide' : ''}`} key={key}><span>{label}</span>{index < 2 ? <input value={draft.worldbook[key]} disabled={busy} onChange={(event) => { setDraft({ ...draft, worldbook: { ...draft.worldbook, [key]: event.target.value } }); setPreview(null); }} /> : <textarea rows={key === 'setting_summary' ? 4 : 3} value={draft.worldbook[key]} disabled={busy} placeholder={key === 'spoiler_notes' ? '仅供译者理解，避免在译文中直接透露' : undefined} onChange={(event) => { setDraft({ ...draft, worldbook: { ...draft.worldbook, [key]: event.target.value } }); setPreview(null); }} />}</label>)}</div>
            </div>
          </div>
        ) : tab === 'characters' ? (
          <div className="workbench-panel"><div className="workbench-character-layout">
            <aside className="workbench-roster"><div className="workbench-roster-header"><strong>角色资料 <span>{draft.characters.length}</span></strong><button className="btn" disabled={busy} onClick={addCharacter}>新增</button></div><input aria-label="搜索角色" placeholder="搜索角色或译名" value={search} onChange={(event) => setSearch(event.target.value)} /><div className="workbench-roster-list">{draft.characters.filter((card) => `${card.name} ${card.name_translation}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map((card) => <button key={card.id} className="workbench-character-item" aria-pressed={selectedId === card.id} onClick={() => setSelectedId(card.id)}><span className="workbench-character-avatar">{(card.name || '?').slice(0, 2)}</span><span><strong>{card.name || '未命名角色'}</strong><small>{card.name_translation || (card.enabled ? '已启用' : '未启用')}</small></span></button>)}{!draft.characters.length && <Empty>新增第一位角色，记录身份与说话风格。</Empty>}</div></aside>
            {selected ? <section className="workbench-card workbench-character-editor"><div className="workbench-editor-header"><div><div className="workbench-card-title">{selected.name || '未命名角色'}</div><div className="workbench-card-hint">正式角色卡 · 保存后用于后续翻译</div></div><button className="btn" disabled={busy} onClick={() => setConfirm('delete')}>删除角色</button></div><div className="workbench-form-grid">{CHARACTER_FIELDS.map(([key, label], index) => <label className={`workbench-field ${index > 1 ? 'workbench-field-wide' : ''}`} key={key}><span>{label}{LIST_FIELDS.has(key) && <small>每行一项</small>}</span>{index < 2 ? <input value={String(selected[key])} disabled={busy} onChange={(event) => updateCharacter(key, event.target.value)} /> : <textarea rows={3} value={Array.isArray(selected[key]) ? (selected[key] as string[]).join('\n') : String(selected[key])} disabled={busy} onChange={(event) => updateCharacter(key, LIST_FIELDS.has(key) ? event.target.value.split('\n') : event.target.value)} />}</label>)}</div><div className="workbench-switch-row"><span>启用此角色</span><Switch checked={selected.enabled} label="启用此角色" disabled={busy} onChange={(value) => updateCharacter('enabled', value)} /></div><div className="workbench-switch-row"><span>主要角色（优先匹配）</span><Switch checked={selected.is_primary} label="主要角色" disabled={busy} onChange={(value) => updateCharacter('is_primary', value)} /></div></section> : <div className="workbench-card"><Empty>选择一位角色，或新增角色资料。</Empty></div>}
          </div></div>
        ) : (
          <div className="workbench-panel"><div className="workbench-card"><div className="workbench-card-title">试一段原文，检查上下文</div><div className="workbench-card-hint">检查已保存资料的角色命中和背景片段；预览不会调用 AI，也不会产生费用。</div><label className="workbench-field"><span>原文样例</span><textarea rows={5} value={sample} disabled={busy} placeholder="输入包含角色名或关键词的原文…" onChange={(event) => { setSample(event.target.value); setPreview(null); }} /></label><div className="workbench-preview-actions"><span className="workbench-card-hint">{dirty ? '先保存修改，再查看最新上下文。' : '匹配遵循实际翻译规则。'}</span><button className="btn btn-primary" disabled={dirty || busy || loading} onClick={() => void previewPrompt()}>生成预览</button></div></div>{preview && <div className="workbench-card"><div className="workbench-card-title">命中角色：{preview.matched_names.join('、') || '无'}</div><pre className="workbench-preview-text">{preview.context || '未产生上下文。请检查资产开关、内容或匹配关键词。'}</pre></div>}</div>
        )}
      </div>
      {confirm === 'delete' && selected && <Dialog title="删除角色资料" confirmText="删除" onCancel={() => setConfirm(null)} onConfirm={() => { if (!draft) return; const cards = draft.characters.filter((card) => card.id !== selected.id); setDraft({ ...draft, characters: cards }); setSelectedId(cards[0]?.id ?? ''); setConfirm(null); setPreview(null); }}>删除「{selected.name}」？点击保存后，删除才会写入当前项目。</Dialog>}
      {confirm === 'reload' && <Dialog title="重新加载项目资料" confirmText="丢弃并重新加载" onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); void reload(); }}>当前未保存的修改将被丢弃。</Dialog>}
      {confirm === 'apply' && <Dialog title="应用已有草稿" confirmText="应用草稿" onCancel={() => setConfirm(null)} onConfirm={() => void applyDrafts()}>草稿将合并到正式世界观和角色资料中，并启用对应上下文。正式资料中的同名字段可能更新。</Dialog>}
    </div>
  );
}