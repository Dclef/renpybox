/** Glossary import parse and duplicate merge. Key matches GlossaryPage normalizeSrc. */
const normalizeKey = (text) => String(text ?? '').replace(/\s+/g, ' ').trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, '').toLowerCase();
const collapsed = (text) => String(text ?? '').replace(/\s+/g, ' ').trim();
const isRecord = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
};
const ERROR = '文件应为词条数组（每项含字符串 src），或原文到译文的映射 {"原文":"译文"}。';

function textOf(value) {
  return typeof value === 'string' ? value : '';
}

function rowFrom(src, fields) {
  const info = fields.info ?? fields.comment ?? '';
  const type = fields.type ?? '';
  return {
    src,
    dst: textOf(fields.dst),
    type: typeof type === 'string' ? type : '',
    info: typeof info === 'string' ? info : '',
    case_sensitive: fields.case_sensitive === true,
    regex: fields.regex === true,
  };
}

export function normalizeImportRows(data) {
  if (Array.isArray(data)) {
    const rows = [];
    for (const item of data) {
      if (!isRecord(item) || typeof item.src !== 'string') return { rows: [], error: ERROR };
      if (!collapsed(item.src)) continue;
      rows.push(rowFrom(item.src, item));
    }
    return { rows, error: '' };
  }
  if (isRecord(data)) {
    const rows = [];
    for (const [src, value] of Object.entries(data)) {
      if (!collapsed(src)) continue;
      if (typeof value === 'string') rows.push(rowFrom(src, { dst: value }));
      else if (isRecord(value)) rows.push(rowFrom(src, value));
      else return { rows: [], error: ERROR };
    }
    return { rows, error: '' };
  }
  return { rows: [], error: ERROR };
}

function shaped(row) {
  return {
    src: String(row.src ?? ''),
    dst: String(row.dst ?? ''),
    type: String(row.type ?? ''),
    info: String(row.info ?? ''),
    case_sensitive: row.case_sensitive === true,
    regex: row.regex === true,
    candidate: false,
    candidate_confirmed: false,
    hits: '',
  };
}

function sameShape(base, next) {
  const keys = Object.keys(next);
  if (Object.keys(base).length !== keys.length) return false;
  return keys.every((key) => base[key] === next[key]);
}

function fillRow(base, incoming) {
  const patch = {};
  const baseDst = String(base.dst ?? '').trim();
  const nextDst = String(incoming.dst ?? '');
  if ((!baseDst || baseDst === String(base.src ?? '').trim()) && nextDst.trim() && nextDst.trim() !== baseDst) patch.dst = nextDst;
  const nextType = String(incoming.type ?? '');
  if (!String(base.type ?? '').trim() && nextType.trim()) patch.type = nextType;
  const nextInfo = String(incoming.info ?? '');
  if (!String(base.info ?? base.comment ?? '').trim() && nextInfo.trim()) patch.info = nextInfo;
  if (incoming.case_sensitive === true && base.case_sensitive !== true) patch.case_sensitive = true;
  if (incoming.regex === true && base.regex !== true) patch.regex = true;
  return Object.keys(patch).length ? { ...base, ...patch } : null;
}

export function mergeImportedRows(current, incoming, strategy) {
  const mode = strategy === 'fill' || strategy === 'overwrite' ? strategy : 'keep';
  const index = new Map();
  for (let i = 0; i < current.length; i += 1) {
    const key = normalizeKey(current[i] && current[i].src);
    if (key && !index.has(key)) index.set(key, i);
  }
  const chosen = new Map();
  const order = [];
  for (const row of incoming) {
    const key = normalizeKey(row && row.src);
    if (!key) continue;
    if (!chosen.has(key)) {
      order.push(key);
      chosen.set(key, row);
    } else if (mode === 'overwrite') chosen.set(key, row);
  }
  let added = 0;
  let duplicate = 0;
  let kept = 0;
  let filled = 0;
  let replaced = 0;
  const appended = [];
  const patches = new Map();
  for (const key of order) {
    const row = chosen.get(key);
    const at = index.get(key);
    if (at == null) {
      added += 1;
      appended.push(shaped(row));
      continue;
    }
    duplicate += 1;
    if (mode === 'keep') {
      kept += 1;
      continue;
    }
    if (mode === 'overwrite') {
      const next = shaped(row);
      if (sameShape(current[at], next)) continue;
      replaced += 1;
      patches.set(at, next);
      continue;
    }
    const next = fillRow(current[at], row);
    if (next) {
      filled += 1;
      patches.set(at, next);
    }
  }
  if (!added && !patches.size) return { rows: current, added, duplicate, kept, filled, replaced };
  const rows = current.slice();
  for (const [at, row] of patches) rows[at] = row;
  for (const row of appended) rows.push(row);
  return { rows, added, duplicate, kept, filled, replaced };
}

const labels = {
  EN: {
    lexicon_import_merge_title: 'Import glossary',
    lexicon_import_merge_summary: '{total} rows in file: {added} new, {duplicate} duplicates. Choose how to handle duplicates:',
    lexicon_import_keep: 'Keep existing (recommended)',
    lexicon_import_keep_desc: 'Duplicates keep current translation and notes; only new terms are appended.',
    lexicon_import_fill: 'Fill blanks only',
    lexicon_import_fill_desc: 'Duplicates only fill empty translations/notes; existing content is untouched.',
    lexicon_import_overwrite: 'Overwrite existing',
    lexicon_import_overwrite_desc: 'Duplicates are replaced by the imported rows.',
    lexicon_import_apply: 'Apply import',
    lexicon_import_merge_toast: 'Added {added}, duplicates {duplicate} (kept {kept} / filled {filled} / replaced {replaced}); save to apply.',
  },
  ZH: {
    lexicon_import_merge_title: '导入术语表',
    lexicon_import_merge_summary: '文件 {total} 条：新增 {added}，与现有重复 {duplicate}。选择重复项处理方式：',
    lexicon_import_keep: '优先保留现有（推荐）',
    lexicon_import_keep_desc: '重复项完全保留现有译文与备注，只追加新词条。',
    lexicon_import_fill: '补齐空白',
    lexicon_import_fill_desc: '重复项仅填充空译文/空备注，已有内容不覆盖。',
    lexicon_import_overwrite: '覆盖现有',
    lexicon_import_overwrite_desc: '重复项用导入内容整行替换。',
    lexicon_import_apply: '应用导入',
    lexicon_import_merge_toast: '新增 {added} 条，重复 {duplicate} 条（保留 {kept} / 补齐 {filled} / 覆盖 {replaced}），保存后生效。',
  },
};

export function importMergeLabels(language) {
  return language === 'EN' ? labels.EN : labels.ZH;
}
