/** Rows the glossary translate request will actually send, with their full-table indexes. */
export function translateTargetRows(rows, checked) {
  const selected = checked && checked.length ? new Set(checked) : null;
  const picked = [];
  const indices = [];
  rows.forEach((row, index) => {
    if (selected && !selected.has(index)) return;
    const src = String(row?.src ?? '').trim();
    const dst = String(row?.dst ?? '').trim();
    if (!src || (dst && dst !== src)) return;
    picked.push(row);
    indices.push(index);
  });
  return { rows: picked, indices };
}

/** Map subset result indexes back onto the full table. Empty or out-of-range indexes are dropped. */
export function mapSubsetResults(indices, results) {
  if (!Array.isArray(indices) || indices.length === 0) return [];
  const mapped = [];
  for (const item of results || []) {
    if (!item || item.length < 2) continue;
    const index = item[0];
    if (!Number.isInteger(index) || index < 0 || index >= indices.length) continue;
    const rowIndex = indices[index];
    if (!Number.isInteger(rowIndex) || rowIndex < 0) continue;
    mapped.push([rowIndex, item[1]]);
  }
  return mapped;
}

export function applyTranslate(rows, results, indices) {
  const next = rows.map((row) => ({ ...row }));
  let applied = 0;
  const items = Array.isArray(indices) ? mapSubsetResults(indices, results) : results;
  for (const item of items || []) {
    if (!item || item.length < 2) continue;
    const index = item[0];
    if (!Number.isInteger(index) || index < 0 || index >= next.length) continue;
    const text = String(item[1] ?? '').trim();
    if (!text) continue;
    const src = String(next[index].src ?? '').trim();
    const current = String(next[index].dst ?? '').trim();
    if (current && current !== src) continue;
    next[index] = { ...next[index], dst: text, candidate_confirmed: next[index].candidate ? true : next[index].candidate_confirmed };
    applied += 1;
  }
  return { rows: next, applied };
}

/** Subset snapshots compare against indices; a missing map keeps the full-table check. */
export function translateSnapshotsMatch(rows, snapshots, indices) {
  if (!Array.isArray(snapshots)) return false;
  if (Array.isArray(indices)) {
    return snapshots.length === indices.length && indices.every((rowIndex, index) => {
      const current = rows[rowIndex];
      const snap = snapshots[index];
      return !!current && snap.src === current.src && snap.dst === current.dst;
    });
  }
  return snapshots.length === rows.length && snapshots.every((row, index) => row.src === rows[index].src && row.dst === rows[index].dst);
}
