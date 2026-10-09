/** 术语表：正式术语与分析候选分别保留，保存复用项目资产仓库。 */
import { useEffect, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Badge, Button, Checkbox, Menu, Textarea, TextInput } from '@mantine/core';
import { Check, Plus, Search } from 'lucide-react';

import { request } from '../api';
import type { AppState } from '../useAppState';
import { Banner, Dialog, Empty, PageHeader } from '../ui';

interface TermRow {
  src: string;
  dst: string;
  info?: string;
  regex?: boolean;
  case_sensitive?: boolean;
  record_id?: string;
  candidate?: boolean;
  candidate_confirmed?: boolean;
  enabled?: boolean;
  type?: string;
  [key: string]: unknown;
}
interface GlossarySnapshot {
  storage_key: string;
  revision: number;
  rows: TermRow[];
  enabled: boolean;
  candidate_ids: string[];
}

export function GlossaryPage({ state, onDirtyChange }: { state: AppState; onDirtyChange?: (dirty: boolean) => void }) {
  const [snapshot, setSnapshot] = useState<GlossarySnapshot | null>(null);
  const [rows, setRows] = useState<TermRow[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [confirmReload, setConfirmReload] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const operation = useRef(0);
  const projectRef = useRef('');
  const projectKey = JSON.stringify([state.project?.renpy_project_path, state.project?.renpy_tl_folder, state.settings?.values.input_folder, state.settings?.values.output_folder]);
  projectRef.current = projectKey;
  const locked = busy || state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  const apply = (next: GlossarySnapshot) => {
    setSnapshot(next); setRows(next.rows); setEnabled(next.enabled); setDirty(false); setError(''); setSelected(null);
  };
  const reload = async () => {
    const id = ++operation.current; const key = projectRef.current;
    setBusy(true);
    try {
      const next = await request<GlossarySnapshot>('/api/workbench/glossary');
      if (id === operation.current && key === projectRef.current) apply(next);
    } catch (e) { if (id === operation.current && key === projectRef.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (id === operation.current && key === projectRef.current) setBusy(false); }
  };
  useEffect(() => {
    operation.current += 1; setBusy(false);
    if (dirtyRef.current) { setError('项目已变更，请先导出未保存的词条，再重新载入当前项目。'); return; }
    let alive = true;
    const id = ++operation.current;
    setBusy(true); setSnapshot(null);
    request<GlossarySnapshot>('/api/workbench/glossary')
      .then(next => { if (alive && id === operation.current) apply(next); })
      .catch(e => { if (alive && id === operation.current) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (alive && id === operation.current) setBusy(false); });
    return () => { alive = false; operation.current += 1; };
  }, [projectKey]);

  const edit = (index: number, patch: Partial<TermRow>) => {
    setRows(previous => previous.map((row, i) => i === index ? { ...row, ...patch } : row)); setDirty(true);
  };
  const save = async () => {
    if (!snapshot || locked) return;
    if (rows.some(row => !row.src.trim())) { setError('请填写每个词条的原文，或删除空词条。'); return; }
    const id = ++operation.current; const key = projectRef.current;
    setBusy(true); setError('');
    try {
      const next = await request<GlossarySnapshot>('/api/workbench/glossary', {
        method: 'PATCH', body: JSON.stringify({ storage_key: snapshot.storage_key, revision: snapshot.revision, candidate_ids: snapshot.candidate_ids, rows, enabled }),
      });
      if (id !== operation.current || key !== projectRef.current) return;
      apply(next); state.pushToast('success', '词库已保存到当前项目');
    } catch (e) { if (id === operation.current && key === projectRef.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (id === operation.current && key === projectRef.current) setBusy(false); }
  };
  const importFile = async (file?: File) => {
    if (!file || locked) return;
    const id = ++operation.current; const key = projectRef.current;
    setBusy(true);
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('JSON 文件应小于 5 MB，请拆分后导入。');
      const data: unknown = JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
      if (!Array.isArray(data) || data.some(row => !row || typeof row !== 'object' || typeof row.src !== 'string' || typeof row.dst !== 'string')) {
        throw new Error('文件应为词条数组，每条至少包含字符串 src 和 dst。');
      }
      // 外部候选保留待确认身份，但不能冒用当前项目的记录 ID。
      const incoming = data.map(row => ({ ...row, record_id: '', candidate: row.candidate === true, candidate_confirmed: false })) as TermRow[];
      if (id !== operation.current || key !== projectRef.current) return;
      setRows(previous => [...previous, ...incoming]); setDirty(true); setError('');
      state.pushToast('info', `已导入 ${incoming.length} 个词条，保存后生效`);
    } catch (e) { if (id === operation.current && key === projectRef.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (id === operation.current && key === projectRef.current) setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  };
  const exportJson = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = 'glossary.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const matched = rows.map((row, index) => ({ row, index })).filter(({ row }) => `${row.src} ${row.dst} ${row.info ?? ''}`.toLowerCase().includes(query.toLowerCase()));
  const candidateCount = rows.filter(row => row.candidate).length;
  const virtualizer = useVirtualizer({
    count: matched.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 40,
    overscan: 8,
  });
  const selectedRow = selected != null ? rows[selected] : undefined;
  const emptyText = busy ? '正在读取词库…' : query ? '没有匹配的词条' : '词库为空，新增或导入词条开始整理';

  return (
    <div className="glossary-layout rb-page">
      <div className="rb-page-scroll rb-glossary">
        <PageHeader
          title="术语表"
          description="当前项目的专有名词对照（角色名、地名、技能等）。保存后翻译会优先采用这些译法；分析产生的候选需确认后才会变成正式词条。"
          actions={(
            <>
              <Button variant="default" disabled={busy} onClick={() => dirty ? setConfirmReload(true) : void reload()}>重新载入</Button>
              <Button disabled={!snapshot || locked || !dirty} onClick={() => void save()}>{busy ? '处理中…' : '保存到项目'}</Button>
            </>
          )}
        />
        <div className="rb-sheet-summary">{rows.length} 个词条 · {candidateCount} 个候选 · {dirty ? '有未保存修改' : '已与项目同步'}</div>
        {error ? <Banner tone="error">{error}</Banner> : null}
        {state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier ? <Banner tone="info">任务执行期间词库只读，结束后可以保存。</Banner> : null}
        <div className="rb-toolbar">
          <TextInput w={280} aria-label="搜索词条" placeholder="搜索原文、译文或备注" value={query} leftSection={<Search size={16} strokeWidth={1.75} />} onChange={(event) => setQuery(event.currentTarget.value)} />
          <Checkbox label="翻译时启用本术语表" checked={enabled} disabled={locked || !snapshot} onChange={(event) => { setEnabled(event.currentTarget.checked); setDirty(true); }} />
          <span className="rb-toolbar-spacer" />
          <Button variant="default" disabled={locked || !snapshot} leftSection={<Plus size={16} strokeWidth={1.75} />} onClick={() => {
            setRows(previous => [{ src: '', dst: '', info: '', candidate: false }, ...previous]);
            setSelected(0); setQuery(''); setDirty(true);
            requestAnimationFrame(() => virtualizer.scrollToOffset(0));
          }}>新增词条</Button>
          <Menu position="bottom-end">
            <Menu.Target><Button variant="default">更多</Button></Menu.Target>
            <Menu.Dropdown>
              <Menu.Item disabled={locked || !snapshot} onClick={() => fileInput.current?.click()}>导入 JSON</Menu.Item>
              <Menu.Item disabled={rows.length === 0} onClick={exportJson}>导出 JSON</Menu.Item>
            </Menu.Dropdown>
          </Menu>
          <input ref={fileInput} type="file" accept=".json,application/json" hidden onChange={e => void importFile(e.target.files?.[0])} />
        </div>
        <div className="rb-sheet">
          <div className="rb-sheet-table" role="table">
            <div className="rb-sheet-head" role="row">
              <span>原文</span><span>译文</span><span>备注</span><span />
            </div>
            <div className="rb-sheet-scroll" ref={listRef}>
              {matched.length === 0 ? <Empty>{emptyText}</Empty> : (
                <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
                  {virtualizer.getVirtualItems().map((item) => {
                    const entry = matched[item.index];
                    if (!entry) return null;
                    const { row, index } = entry;
                    return (
                      <div
                        key={item.key}
                        className="rb-term-row"
                        role="row"
                        data-selected={selected === index ? 'true' : undefined}
                        tabIndex={0}
                        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: 40, transform: `translateY(${item.start}px)` }}
                        onClick={() => setSelected(index)}
                        onKeyDown={(event) => { if (event.key === 'Enter') setSelected(index); }}
                      >
                        <span>{row.src}</span>
                        <span>{row.dst}</span>
                        <span>{row.info}</span>
                        <span className="rb-term-marks">
                          {row.candidate ? <Badge>{row.candidate_confirmed ? <Check size={12} strokeWidth={1.75} /> : null}候选</Badge> : null}
                          {row.case_sensitive ? <Badge title="区分大小写">Aa</Badge> : null}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="rb-sheet-foot">{matched.length} 条</div>
          </div>
          {selectedRow ? (
            <aside className="rb-term-editor">
              <header>
                <h2>词条 {selected! + 1}</h2>
                <Button variant="default" size="xs" onClick={() => setSelected(null)}>完成</Button>
              </header>
              <Textarea autosize label="原文" disabled={locked} value={selectedRow.src} onChange={(event) => edit(selected!, { src: event.currentTarget.value })} />
              <Textarea autosize label="译文" disabled={locked} value={selectedRow.dst} onChange={(event) => edit(selected!, { dst: event.currentTarget.value })} />
              <TextInput placeholder="备注（可选）" disabled={locked} value={selectedRow.info ?? ''} onChange={(event) => edit(selected!, { info: event.currentTarget.value })} />
              <Checkbox label="区分大小写" checked={selectedRow.case_sensitive === true} disabled={locked} onChange={(event) => edit(selected!, { case_sensitive: event.currentTarget.checked })} />
              {selectedRow.candidate
                ? <Checkbox label="确认候选" checked={selectedRow.candidate_confirmed === true} disabled={locked || !selectedRow.dst.trim()} onChange={(event) => edit(selected!, { candidate_confirmed: event.currentTarget.checked })} />
                : <span className="rb-term-formal">正式词条</span>}
              <Button color="red" variant="subtle" disabled={locked} onClick={() => { setRows(previous => previous.filter((_, i) => i !== selected)); setSelected(null); setDirty(true); }}>移除</Button>
            </aside>
          ) : null}
        </div>
      </div>
      {confirmReload ? <Dialog title="放弃未保存的修改？" confirmText="重新载入" onCancel={() => setConfirmReload(false)} onConfirm={() => { setConfirmReload(false); void reload(); }}>重新载入会用项目中的词库替换当前编辑。</Dialog> : null}
    </div>
  );
}
