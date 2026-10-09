/** 平行校对台：分页读取真实缓存，保存前由服务端检查项目和译文版本。 */
import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import type { AppState } from '../useAppState';
import { Button, Checkbox, Select, Textarea, TextInput, UnstyledButton } from '@mantine/core';
import { DataSheet } from '../components/DataSheet';
import { Banner, Dialog, PageHeader } from '../ui';

interface ProofreadingRow {
  id: number;
  version: string;
  src: string;
  dst: string;
  status: string;
  file_path: string;
  row: number;
}

interface ProofreadingData {
  cache_token: string;
  cache_folder: string;
  total: number;
  matched: number;
  page: number;
  limit: number;
  files: string[];
  readonly: boolean;
  items: ProofreadingRow[];
}

const STATUS_LABELS: Record<string, string> = {
  UNTRANSLATED: '待翻译', TRANSLATED: '已翻译', POLISHED: '已润色',
  TRANSLATED_IN_PAST: '已有译文', EXCLUDED: '已排除', DUPLICATED: '重复',
};

export function ProofreadingPage({ state, onDirtyChange }: {
  state: AppState;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [data, setData] = useState<ProofreadingData | null>(null);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [file, setFile] = useState('');
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [edit, setEdit] = useState<(ProofreadingRow & { cache_token: string; project_identity: string }) | null>(null);
  const [draft, setDraft] = useState('');
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [replaceSnapshot, setReplaceSnapshot] = useState<{ cache_token: string; rows: ProofreadingRow[] } | null>(null);
  const [find, setFind] = useState('');
  const [replacement, setReplacement] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(true);
  const requestId = useRef(0);
  const projectRef = useRef('');
  const dirtyRef = useRef(false);
  const projectIdentity = JSON.stringify([
    state.project?.renpy_project_path, state.project?.renpy_game_folder, state.project?.renpy_tl_folder,
    state.settings?.values.input_folder, state.settings?.values.output_folder,
  ]);
  projectRef.current = projectIdentity;
  const editProjectChanged = Boolean(edit && edit.project_identity !== projectIdentity);
  const readonly = data?.readonly || state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier || state.translation.single_tasks;
  const dirty = Boolean(edit && draft !== edit.dst);
  dirtyRef.current = dirty;

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    setData(null);
    setSelected(new Set());
    if (!dirtyRef.current) setEdit(null);
    setReplaceOpen(false);
    setPage(1);
    setFile('');
  }, [projectIdentity]);

  useEffect(() => state.subscribe((event) => {
    if (['TRANSLATION_DONE', 'PROJECT_STATUS_CHECK_DONE'].includes(event.event)) {
      setRefresh((value) => value + 1);
    }
  }), [state.subscribe]);

  useEffect(() => {
    if (!state.ready) return;
    const id = ++requestId.current;
    const params = new URLSearchParams({ page: String(page), limit: '50', query: search, status, file_path: file });
    setLoading(true);
    setError('');
    request<ProofreadingData>(`/api/proofreading?${params}`)
      .then((result) => {
        if (id !== requestId.current) return;
        setData(result);
        setSelected(new Set());
        if (result.page !== page) setPage(result.page);
      })
      .catch((failure: unknown) => {
        if (id !== requestId.current) return;
        setData(null);
        setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => { if (id === requestId.current) setLoading(false); });
    return () => { requestId.current += 1; };
  }, [state.ready, projectIdentity, page, search, status, file, refresh]);

  const reload = () => setRefresh((value) => value + 1);
  const closeEdit = () => {
    if (saving) return;
    if (dirty && !window.confirm('译文尚未保存，确定放弃这次编辑？')) return;
    setEdit(null);
  };

  const saveEdit = async () => {
    if (!data || !edit || saving || readonly || editProjectChanged) return;
    const identity = projectRef.current;
    setSaving(true);
    try {
      await request('/api/proofreading/item', {
        method: 'PATCH', body: JSON.stringify({
          cache_token: edit.cache_token, row: { id: edit.id, version: edit.version }, dst: draft,
        }),
      });
      if (identity !== projectRef.current) return;
      setEdit(null);
      state.pushToast('success', '译文已保存到当前项目缓存。');
      reload();
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally { setSaving(false); }
  };

  const replaceRows = async () => {
    if (!replaceSnapshot || !find || saving || readonly) return;
    const targets = replaceSnapshot.rows;
    setSaving(true);
    try {
      const result = await request<{ changed: number }>('/api/proofreading/replace', {
        method: 'POST', body: JSON.stringify({
          cache_token: replaceSnapshot.cache_token,
          rows: targets.map((row) => ({ id: row.id, version: row.version })),
          find, replace: replacement, case_sensitive: caseSensitive,
        }),
      });
      setReplaceOpen(false);
      state.pushToast(result.changed ? 'success' : 'info', result.changed ? `已替换并保存 ${result.changed} 条译文。` : '没有匹配的译文，内容未改变。');
      reload();
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally { setSaving(false); }
  };

  const items = data?.items ?? [];
  const toggle = (key: string) => {
    const id = Number(key);
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const openEdit = (row: ProofreadingRow) => {
    setEdit({ ...row, cache_token: data?.cache_token ?? '', project_identity: projectIdentity });
    setDraft(row.dst);
  };

  return (
    <div className="proofreading-page rb-page">
      <div className="rb-page-scroll">
        <PageHeader
          title="平行校对台"
          description="原文与译文并排阅读，让每一句更准确、更自然。"
          actions={(
            <>
              <Button variant="default" disabled={loading || saving} onClick={reload}>刷新译文</Button>
              <Button variant="default" disabled={readonly || loading || saving || !data?.items.length} onClick={() => { if (!data) return; setReplaceSnapshot({ cache_token: data.cache_token, rows: selected.size ? data.items.filter((row) => selected.has(row.id)) : data.items }); setReplaceOpen(true); }}>批量替换</Button>
            </>
          )}
        />
        {readonly && <Banner tone="info">当前任务正在运行，译文可阅读；任务结束后可以编辑和保存。</Banner>}
        {error && <Banner tone="warning">{error}</Banner>}
        <form className="proofreading-filters" onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(query.trim()); }}>
          <TextInput aria-label="搜索原文或译文" placeholder="搜索原文、译文或文件…" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
          <Select aria-label="翻译状态" allowDeselect={false} value={status} data={[{ value: '', label: '全部状态' }, ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))]} onChange={(value) => { if (value != null) { setStatus(value); setPage(1); } }} />
          <Select aria-label="源文件" allowDeselect={false} value={file} data={[{ value: '', label: '全部文件' }, ...(data?.files ?? []).map((path) => ({ value: path, label: path || '未分类' }))]} onChange={(value) => { if (value != null) { setFile(value); setPage(1); } }} />
          <Button variant="default" type="submit" disabled={loading}>搜索</Button>
        </form>
        <DataSheet
          virtual={false}
          rows={items}
          getKey={(row) => String(row.id)}
          selectedKey={edit ? String(edit.id) : null}
          onSelect={() => undefined}
          emptyText={data ? '没有符合筛选条件的译文。' : '先完成一次翻译，再来这里打磨对白。'}
          selection={{
            keys: new Set([...selected].map(String)),
            disabled: Boolean(readonly || loading),
            onToggle: toggle,
            onToggleAll: (checked) => setSelected(checked ? new Set(items.map((row) => row.id)) : new Set()),
          }}
          columns={[
            { key: 'index', title: '序号', width: '72px', render: (row) => <span>{row.id + 1}</span> },
            { key: 'status', title: '状态', width: '120px', render: (row) => <span className="rb-proof-status" data-status={row.status}><i />{STATUS_LABELS[row.status] ?? row.status}</span> },
            { key: 'src', title: '原文', render: (row) => <span>{row.src}</span> },
            { key: 'dst', title: '译文', render: (row) => (
              <UnstyledButton className="proofreading-target" disabled={readonly || loading || saving} onClick={(event) => { event.stopPropagation(); openEdit(row); }}>
                {row.dst || '（空，点击编辑）'}
              </UnstyledButton>
            ) },
            { key: 'file', title: '文件', width: '180px', render: (row) => <span>{`${row.file_path || '未分类'}${row.row ? `:${row.row}` : ''}`}</span> },
          ]}
          editorClassName="rb-term-editor"
          editor={edit ? (
            <>
              <header><h2>打磨译文</h2></header>
              {editProjectChanged && <Banner tone="warning">项目已切换，未保存的译文已保留。请先复制译文，再取消编辑并载入新项目。</Banner>}
              <div className="proofreading-editor-source">{edit.src}</div>
              <Textarea id="proofreading-draft" autosize minRows={7} value={draft} disabled={saving || readonly} onChange={(event) => setDraft(event.currentTarget.value)} />
              <span className="rb-term-formal">{saving ? '正在保存…' : '保存到翻译缓存；写回游戏请使用翻译页的“导出译文”。'}</span>
              <div className="rb-dialog-actions">
                <Button variant="default" onClick={closeEdit}>取消</Button>
                <Button disabled={saving || readonly || !dirty || editProjectChanged} onClick={() => void saveEdit()}>保存译文</Button>
              </div>
            </>
          ) : null}
        />
        <footer className="proofreading-pagination">
          <span>{data ? `${data.matched.toLocaleString()} 条符合条件 · 共 ${data.total.toLocaleString()} 条` : '原译对照'}{selected.size ? ` · 已选 ${selected.size} 条` : ''}</span>
          <div className="proofreading-toolbar">
            <Button variant="default" size="xs" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</Button>
            <span>{data?.page ?? 1} / {Math.max(1, Math.ceil((data?.matched ?? 0) / 50))}</span>
            <Button variant="default" size="xs" disabled={loading || !data || page * 50 >= data.matched} onClick={() => setPage((value) => value + 1)}>下一页</Button>
          </div>
        </footer>
      </div>
      {replaceOpen && (
        <Dialog title="批量替换译文" confirmText="替换并保存" onCancel={() => { if (!saving) setReplaceOpen(false); }} onConfirm={!find || saving || readonly ? undefined : () => void replaceRows()}>
          <p>对{selected.size ? `已选 ${selected.size} 条` : `当前页 ${replaceSnapshot?.rows.length ?? 0} 条`}译文执行纯文本替换，并立即保存。</p>
          <div className="proofreading-replacement-grid">
            <TextInput label="查找" value={find} disabled={saving} placeholder="需要替换的内容" onChange={(event) => setFind(event.currentTarget.value)} />
            <TextInput label="替换为" value={replacement} disabled={saving} placeholder="留空可删除匹配内容" onChange={(event) => setReplacement(event.currentTarget.value)} />
          </div>
          <Checkbox label="区分大小写" checked={caseSensitive} disabled={saving} onChange={(event) => setCaseSensitive(event.currentTarget.checked)} />
          {saving && <p>正在保存替换结果…</p>}
        </Dialog>
      )}
    </div>
  );
}
