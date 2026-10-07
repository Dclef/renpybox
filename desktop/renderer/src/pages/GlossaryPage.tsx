/** 项目词库：正式术语与分析候选分别保留，保存复用项目资产仓库。 */
import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import type { AppState } from '../useAppState';
import { Banner, Dialog, Empty } from '../ui';

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
const PAGE_SIZE = 40;

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
  const [page, setPage] = useState(0);
  const [confirmReload, setConfirmReload] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
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
    setSnapshot(next); setRows(next.rows); setEnabled(next.enabled); setDirty(false); setError(''); setPage(0);
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
  const pageCount = Math.max(1, Math.ceil(matched.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = matched.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const candidateCount = rows.filter(row => row.candidate).length;

  return (
    <div className="settings-layout glossary-layout">
      <header className="settings-header">
        <h1 className="settings-title">项目词库</h1>
        <p className="settings-subtitle">统一专有名词译法，确认候选后用于下一次翻译</p>
      </header>
      <div className="settings-scroll glossary-scroll">
        <div className="workspace-toolbar">
          <div className="workspace-summary"><strong>{rows.length} 个词条</strong><span>{candidateCount} 个候选 · {dirty ? '有未保存修改' : '已与项目同步'}</span></div>
          <div className="workspace-actions">
            <button className="btn" disabled={busy} onClick={() => dirty ? setConfirmReload(true) : void reload()}>重新载入</button>
            <button className="btn btn-primary" disabled={!snapshot || locked || !dirty} onClick={() => void save()}>{busy ? '处理中…' : '保存到项目'}</button>
          </div>
        </div>
        {error ? <Banner tone="error">{error}</Banner> : null}
        <div className="workspace-toolbar glossary-tools">
          <input type="text" aria-label="搜索词条" placeholder="搜索原文、译文或备注" value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} />
          <div className="workspace-actions">
            <button className="btn" disabled={locked || !snapshot} onClick={() => { setRows(previous => [{ src: '', dst: '', info: '', candidate: false }, ...previous]); setQuery(''); setPage(0); setDirty(true); }}>新增词条</button>
            <button className="btn" disabled={locked || !snapshot} onClick={() => fileInput.current?.click()}>导入 JSON</button>
            <button className="btn" disabled={rows.length === 0} onClick={exportJson}>导出 JSON</button>
            <input ref={fileInput} type="file" accept=".json,application/json" hidden onChange={e => void importFile(e.target.files?.[0])} />
          </div>
        </div>
        <label className="checkbox-label"><input type="checkbox" disabled={locked || !snapshot} checked={enabled} onChange={e => { setEnabled(e.target.checked); setDirty(true); }} />在翻译中启用项目词库</label>
        {state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier ? <Banner tone="info">任务执行期间词库只读，结束后可以保存。</Banner> : null}
        <div className="glossary-list">
          <div className="glossary-column-head"><span>原文</span><span>译文</span><span>操作</span></div>
          {visible.map(({ row, index }) => (
            <div className="glossary-row" key={`${index}-${row.record_id ?? ''}`}>
              <textarea aria-label={`词条 ${index + 1} 原文`} value={row.src} disabled={locked} onChange={e => edit(index, { src: e.target.value })} rows={2} />
              <textarea aria-label={`词条 ${index + 1} 译文`} value={row.dst} disabled={locked} onChange={e => edit(index, { dst: e.target.value })} rows={2} />
              <button className="btn btn-danger" disabled={locked} onClick={() => { setRows(previous => previous.filter((_, i) => i !== index)); setDirty(true); }}>移除</button>
              <input className="glossary-note" type="text" aria-label={`词条 ${index + 1} 备注`} placeholder="备注（可选）" value={row.info ?? ''} disabled={locked} onChange={e => edit(index, { info: e.target.value })} />
              <div className="glossary-options">
                {row.candidate ? <label className="checkbox-label"><input type="checkbox" checked={row.candidate_confirmed === true} disabled={locked || !row.dst.trim()} onChange={e => edit(index, { candidate_confirmed: e.target.checked })} />确认候选</label> : <span className="card-description">人工 / 正式词条</span>}
                <label className="checkbox-label"><input type="checkbox" checked={row.case_sensitive === true} disabled={locked} onChange={e => edit(index, { case_sensitive: e.target.checked })} />区分大小写</label>
              </div>
            </div>
          ))}
          {visible.length === 0 ? <Empty>{busy ? '正在读取词库…' : query ? '没有匹配的词条' : '词库为空，新增或导入词条开始整理'}</Empty> : null}
        </div>
        <div className="workspace-toolbar pagination-bar">
          <span className="card-description">{matched.length} 条 · 第 {currentPage + 1} / {pageCount} 页</span>
          <div className="workspace-actions"><button className="btn" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一页</button><button className="btn" disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>下一页</button></div>
        </div>
      </div>
      {confirmReload ? <Dialog title="放弃未保存的修改？" confirmText="重新载入" onCancel={() => setConfirmReload(false)} onConfirm={() => { setConfirmReload(false); void reload(); }}>重新载入会用项目中的词库替换当前编辑。</Dialog> : null}
    </div>
  );
}
