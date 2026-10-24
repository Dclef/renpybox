/**
 * 关系图谱空态的「卡点判定」：把项目体检结果翻译成一张引导卡。
 *
 * 关系图谱的数据只来自规则挖掘（RelationMiner 读 game 目录下的 .rpy，找
 * 「称谓词 + 同场景角色变量」），所以它既不需要世界观，也不需要先翻译。
 * 真正的前置只有三步：绑工程 → 有 .rpy → 扫一次。这里把「现在缺哪一步」
 * 判定成唯一的一个动作，免得用户在空页面上猜。
 */

/** 体检结果里跟这里有关的字段（其余字段不参与判定）。 */
function stageOf(readiness) {
  const stage = readiness && typeof readiness === 'object' ? readiness.stage : null;
  return typeof stage === 'string' && stage ? stage : null;
}

/**
 * 判定当前该显示哪张引导卡。
 *
 * @param {object|null|undefined} readiness 项目体检结果；null 表示还没拿到。
 * @returns {{
 *   stage: string,
 *   title: string,
 *   detail: string,
 *   action: 'scan' | 'bind' | 'unpack' | null,
 *   actionLabel: string,
 * }}
 */
export function resolveGraphBlocked(readiness) {
  const stage = stageOf(readiness);
  const rpyFiles = Number(readiness && readiness.rpy_files) || 0;
  const rpaFiles = Number(readiness && readiness.rpa_files) || 0;

  // 体检结果还没回来：仍然要给出扫描入口，否则页面是纯死胡同。
  if (stage === null) {
    return {
      stage: 'unknown',
      title: '还没有角色资料',
      detail: '关系图谱靠扫描 game 目录里的脚本挖出来，先扫一次就有了。',
      action: 'scan',
      actionLabel: '扫描角色',
    };
  }

  if (stage === 'unbound' || stage === 'no_game') {
    return {
      stage,
      title: '先绑定 Ren’Py 工程',
      detail: '关系图谱要读游戏目录里的 .rpy 脚本，才知道谁跟谁怎么称呼。现在还没有可用的游戏目录。',
      action: 'bind',
      actionLabel: '去绑定工程',
    };
  }

  if (stage === 'packed') {
    return {
      stage,
      title: '这个游戏还没解包',
      detail: `目录里只有 ${rpaFiles} 个 .rpa 打包文件，没有 .rpy 源码，扫不出任何角色。先去工具箱解包，回来再扫。`,
      action: 'unpack',
      actionLabel: '去解包',
    };
  }

  if (stage === 'no_script') {
    return {
      stage,
      title: '这个目录里没有脚本',
      detail: '既没有 .rpy 也没有 .rpa。确认绑定的是游戏的根目录（里面应该有 game 文件夹）。',
      action: 'bind',
      actionLabel: '重新选目录',
    };
  }

  // ready：前置全齐，纯粹是还没扫过。
  return {
    stage: 'ready',
    title: '还没扫描过角色',
    detail: `工程里有 ${rpyFiles} 个脚本，扫描会从中找出所有说话人，再按称谓规则挖出有原文证据的关系。`
      + '不需要先翻译，也不用先生成世界观。',
    action: 'scan',
    actionLabel: '扫描角色',
  };
}

/**
 * 扫描按钮被禁用时的原因文案；可用时返回空串。
 *
 * 禁用有多个来源（引擎忙 / 有未保存改动 / 正在分析），这里不区分细节，
 * 只提醒用户「先处理完」，避免按钮灰着却没有任何解释。
 *
 * @param {boolean} canScan
 * @returns {string}
 */
export function scanBlockedHint(canScan) {
  return canScan ? '' : '有未保存的改动或引擎正忙，先处理完再扫描。';
}
