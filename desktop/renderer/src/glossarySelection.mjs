/** Checked deletion is distinct from the active row used by click/Enter/F2. */
const asIndex = (key, count) => {
  if (typeof key === 'string' && !/^(0|[1-9]\d*)$/.test(key)) return null;
  if (typeof key !== 'string' && typeof key !== 'number') return null;
  const index = Number(key);
  return Number.isSafeInteger(index) && index >= 0 && index < count ? index : null;
};
export function selectionContextChanged(value, context) {
  return Boolean(value && typeof value === 'object' && value.context !== context);
}
export function readRowSelection(value, count, context) {
  if (typeof value === 'number') return { active: asIndex(value, count), checked: [], context };
  if (!value || typeof value !== 'object' || selectionContextChanged(value, context)) return { active: null, checked: [], context };
  const checked = [...new Set((Array.isArray(value.checked) ? value.checked : []).map(key => asIndex(key, count)).filter(key => key != null))].sort((a, b) => a - b);
  return { active: asIndex(value.active, count), checked, context };
}
export function selectActiveRow(value, key, count, context) {
  return { ...readRowSelection(value, count, context), active: asIndex(key, count) };
}
export function selectCheckedRows(value, keys, count, context) {
  return readRowSelection({ ...readRowSelection(value, count, context), checked: keys }, count, context);
}
export function deleteCheckedRows(rows, value, context) {
  const checked = new Set(readRowSelection(value, rows.length, context).checked);
  return checked.size ? rows.filter((_row, index) => !checked.has(index)) : rows;
}
export function clearCheckedTranslations(rows, value, context) {
  const checked = new Set(readRowSelection(value, rows.length, context).checked);
  if (!checked.size) return { rows, changed: 0 };
  let changed = 0;
  const next = rows.map((row, index) => {
    if (!checked.has(index)) return row;
    if (row.dst.trim() !== '') changed += 1;
    return { ...row, dst: '' };
  });
  return { rows: next, changed };
}

// Local labels avoid replacing the shared language Context while drafts are live.
const labels = {
  ZH: {
    deleteSelected: '删除所选（{count}）', selectPage: '选择本页全部词条',
    selectRow: '选择第 {index} 行', selectedCount: '已选 {count} 条（跨页保留）', confirmCurrent: '确认当前行',
  },
  EN: {
    deleteSelected: 'Delete selected ({count})', selectPage: 'Select all entries on this page',
    selectRow: 'Select row {index}', selectedCount: '{count} selected (across pages)', confirmCurrent: 'Confirm current row',
  },
};
export function glossarySelectionLabels(language) {
  return language === 'EN' ? labels.EN : labels.ZH;
}

