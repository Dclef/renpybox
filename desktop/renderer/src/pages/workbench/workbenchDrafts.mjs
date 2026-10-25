/**
 * 工作台「草稿横幅」和「AI 动作按钮」的判定：把实时快照里的草稿数翻译成一句不矛盾的话。
 *
 * 用户实测的坑：扫描完是 2 张草稿，横幅写着「角色草稿 2 张，请审核后应用」，
 * 可清洗/应用完之后快照里已经是 0 张，横幅却还停在扫描那一刻的数字上，
 * 右上角同时写着「待审核草稿 0 张」——两块界面自相矛盾，用户只看到按钮全灰。
 *
 * 所以这里只认「实时快照」的数字：横幅、按钮文案、按钮置灰的原因都从同一份计数派生，
 * 清洗 / 应用 / 重扫后快照一变，文案立刻跟着变。判定写成纯函数，方便 node 单测盯住。
 * 文案与 graphBlocked.mjs 同口径直接写在这里：这两块都是中文界面的引导文案。
 */

/** 计数兜底：缺字段 / NaN / 负数一律按 0，绝不让 NaN 漏到文案里。 */
function toCount(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}

/**
 * 顶部草稿横幅：草稿为 0 时不再说「请审核后应用 N 张」。
 *
 * @param {{
 *   characters?: number,
 *   worldbook?: number,
 *   generatedCharacters?: number,
 *   generatedWorldbook?: number,
 * }} [input]
 *   characters / worldbook 是实时快照里的草稿数；generatedCharacters / generatedWorldbook 是
 *   上一次扫描声称生成了多少（只用来判断「刚才确实有草稿，现在是 0」＝已经被应用了）。
 * @returns {{ visible: boolean, tone: 'pending' | 'applied' | 'none', message: string }}
 */
export function resolveDraftNotice(input) {
  const source = input && typeof input === 'object' ? input : {};
  const characters = toCount(source.characters);
  const worldbook = toCount(source.worldbook);
  const generated = toCount(source.generatedCharacters) + toCount(source.generatedWorldbook);

  const parts = [];
  if (worldbook > 0) parts.push(`世界观草稿 ${worldbook} 项`);
  if (characters > 0) parts.push(`角色草稿 ${characters} 张`);

  if (parts.length) {
    // 只报真实存在的草稿：0 张的那一类干脆不出现，避免「请审核后应用 0 张」这种废话。
    const applied = characters === 0 && generated > 0 ? '；角色草稿已全部应用到角色资料。' : '';
    return {
      visible: true,
      tone: 'pending',
      message: `${parts.join(' · ')}，请审核后应用。${applied}`,
    };
  }

  // 草稿全为 0：刚扫出来又被应用掉的话给一句收尾说明，否则直接收起横幅。
  if (generated > 0) {
    return {
      visible: true,
      tone: 'applied',
      message: '扫描出的草稿已全部应用到正式资料，当前没有待审核草稿。',
    };
  }

  return { visible: false, tone: 'none', message: '' };
}

/**
 * 「AI 推断关系」能处理多少对角色：只数同场共现、且没有人工/否决边挡路的角色对。
 *
 * - 同场共现两侧各存一遍，按无向对去重，只算一次；
 * - 对方不在名册里的记录后端也写不了，这里先排除，避免按钮上的数字虚高；
 * - 已有 manual/rejected 边的对后端会整对跳过，前端同样不把它算进可推断数；
 * - 已有 ai 边的对仍然算：再点一次就是用新资料重算，不是重复劳动。
 */
export function countInferablePairs(characters) {
  const list = Array.isArray(characters) ? characters : [];
  const byName = new Map();
  for (const card of list) {
    const name = String(card?.name ?? '').trim().toLowerCase();
    if (name) byName.set(name, card);
  }
  // 人工/否决边是用户既有结论，后端整对跳过，前端计数口径必须一致。
  const pinned = new Set();
  for (const card of list) {
    const name = String(card?.name ?? '').trim().toLowerCase();
    if (!name) continue;
    for (const relation of card?.relations ?? []) {
      const source = String(relation?.source ?? '').toLowerCase();
      if (source !== 'manual' && source !== 'rejected') continue;
      const target = String(relation?.target ?? '').trim().toLowerCase();
      if (target) pinned.add([name, target].sort().join('\u0000'));
    }
  }
  const seen = new Set();
  let count = 0;
  for (const card of list) {
    const name = String(card?.name ?? '').trim().toLowerCase();
    if (!name) continue;
    for (const [targetRaw, hitRaw] of Object.entries(card?.co_occurrence ?? {})) {
      const target = String(targetRaw ?? '').trim().toLowerCase();
      const hit = Number(hitRaw);
      if (!target || target === name || !(hit > 0) || !byName.has(target)) continue;
      const pair = [name, target].sort().join('\u0000');
      if (pinned.has(pair) || seen.has(pair)) continue;
      seen.add(pair);
      count += 1;
    }
  }
  return count;
}

/**
 * AI 清洗 / AI 复核 / AI 推断按钮的状态：文案、能不能点、置灰时那句可见的原因。
 *
 * 置灰原因按优先级给第一条：
 *   1. 本来就没有可做的对象（无草稿 / 无规则边 / 无同场共现）；
 *   2. 模型正在处理上一条请求；
 *   3. 有未保存改动、分析任务在跑之类的通用占用。
 * 可见的原因必须挂在按钮旁边（不是只塞 title），用户不用猜。
 *
 * @param {{ mode?: 'clean' | 'review' | 'infer', count?: number, reviewing?: boolean, disabled?: boolean }} [input]
 * @returns {{ mode: 'clean' | 'review' | 'infer', count: number, blocked: boolean, label: string, hint: string }}
 */
export function resolveAiAction(input) {
  const source = input && typeof input === 'object' ? input : {};
  const mode = source.mode === 'review' ? 'review' : source.mode === 'infer' ? 'infer' : 'clean';
  const count = toCount(source.count);
  const reviewing = Boolean(source.reviewing);
  const disabled = Boolean(source.disabled);
  const blocked = disabled || reviewing || count === 0;
  const name = mode === 'clean' ? 'AI 清洗角色' : mode === 'infer' ? 'AI 推断关系' : 'AI 复核关系';
  // 有对象时把数量写进按钮，用户一眼知道点下去要处理多少条；推断按「对」计数。
  const label = count > 0
    ? (mode === 'infer' ? `${name} · ${count} 对` : `${name} · ${count}`)
    : name;

  let hint = '';
  if (count === 0) {
    hint = mode === 'clean'
      ? '没有待清洗的角色草稿 · 重新分析后会出现'
      : mode === 'infer'
        ? '这些角色之间没有同场记录 · 先跑一次角色扫描'
        : '规则还没挖到关系证据 · 可在角色卡手动补一条';
  } else if (reviewing) {
    hint = '模型正在处理上一条请求 · 结束后可再点';
  } else if (blocked) {
    hint = '有未保存的改动或任务正忙 · 处理完可再点';
  }

  return { mode, count, blocked, label, hint };
}
