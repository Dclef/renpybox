/**
 * 游戏模组注入纯函数与双语文案（就地 const）。
 * 对齐 Qt5 GameModPage：路径初空、三固定键、legacy 双文件清理。
 */

export const MOD_KEYS = ['gallery_unlock', 'urm', 'simple_modifier'];

export const MOD_COPY = {
  title: { ZH: '游戏模组注入', EN: 'Game Mod Injection' },
  intro: {
    ZH: '画廊解锁器由 ZLZK 提供，修改器由 0x52 提供；游戏内 MOD 面板由 RenpyBox 提供。仅支持 PC / 模拟器版，不支持安卓版。',
    EN: 'Gallery unlocker by ZLZK, utility by 0x52, in-game MOD panel by RenpyBox. PC/emulator only; Android is not supported.',
  },
  gameDir: { ZH: '游戏目录', EN: 'Game Folder' },
  gameHint: {
    ZH: '选择项目根目录或 game 目录；路径为空时状态未知。',
    EN: 'Select the project root or game folder. Status is unknown when empty.',
  },
  browse: { ZH: '浏览', EN: 'Browse' },
  install: { ZH: '安装', EN: 'Install' },
  uninstall: { ZH: '卸载', EN: 'Uninstall' },
  installed: { ZH: '已安装', EN: 'Installed' },
  notInstalled: { ZH: '未安装', EN: 'Not installed' },
  unknown: { ZH: '未选择游戏目录', EN: 'no game folder selected' },
  galleryTitle: {
    ZH: '解锁画廊（ZLZK 通用画廊解锁器改写版）',
    EN: 'Gallery Unlocker (adapted from the ZLZK universal gallery unlocker)',
  },
  galleryDesc: {
    ZH: '安装后游戏右上角会显示“MOD”按钮；F9 打开面板，F10 直接切换画廊状态。',
    EN: 'Adds a MOD button at the top right. Press F9 to open the panel or F10 to toggle the gallery.',
  },
  urmTitle: { ZH: '修改器（0x52-URM 2.6.2 汉化版）', EN: 'Utility Mod (0x52-URM 2.6.2 Chinese edition)' },
  urmDesc: {
    ZH: '将修改器和游戏内按钮注入 game/，也可按 Alt+M 唤出。',
    EN: 'Injects the utility and an in-game button into game/. Press Alt+M to open it.',
  },
  simpleTitle: { ZH: '内置修改器（RenpyBox）', EN: 'Built-in Utility (RenpyBox)' },
  simpleDesc: {
    ZH: '提供对话框、选项框和快捷菜单调整；可单独安装，也可与画廊解锁器同时使用。',
    EN: 'Adjusts dialogue boxes, choice screens, and the quick menu. Can be installed alone or with the gallery unlocker.',
  },
  legacyWarn: {
    ZH: '检测到旧版独木桥，删除后重启游戏，避免覆盖原游戏菜单。',
    EN: 'A legacy Dumuqiao install was found. Remove it and restart the game to avoid replacing the original menu.',
  },
  legacyClean: { ZH: '删除旧版独木桥', EN: 'Remove Legacy Dumuqiao' },
  legacyConfirm: {
    ZH: '将永久删除 game/dumuqiao.rpy 与 game/dumuqiao.rpyc。不会删除 .bak 或其他用户脚本。是否继续？',
    EN: 'This permanently deletes game/dumuqiao.rpy and game/dumuqiao.rpyc. Backups and other user scripts are not removed. Continue?',
  },
  installConfirm: {
    ZH: '将写入固定模组文件；若目标已存在会备份为 .bak。卸载不会自动恢复 .bak。是否继续？',
    EN: 'This writes fixed mod files. Existing targets are renamed to .bak. Uninstall does not restore .bak. Continue?',
  },
  uninstallConfirm: {
    ZH: '将删除固定模组文件与对应 .rpyc，不会自动从 .bak 恢复。是否继续？',
    EN: 'This removes the fixed mod files and matching .rpyc files. .bak is not restored. Continue?',
  },
  needGame: { ZH: '请选择项目根目录或 game 目录', EN: 'Select the project root or game folder.' },
};

export function modCopy(table, lang = 'ZH') {
  return table[lang === 'EN' ? 'EN' : 'ZH'] || table.ZH;
}

export function gameModStatusPath(gamePath = '') {
  const trimmed = String(gamePath || '').trim();
  if (!trimmed) return '/api/game-mod?game_path=';
  return `/api/game-mod?game_path=${encodeURIComponent(trimmed)}`;
}

export function gamePathReady(gamePath = '') {
  return Boolean(String(gamePath || '').trim());
}

export function modStatusLabel(installed, lang = 'ZH') {
  return installed ? modCopy(MOD_COPY.installed, lang) : modCopy(MOD_COPY.notInstalled, lang);
}

export function isSupportedModKey(key) {
  return MOD_KEYS.includes(String(key || ''));
}

/** 从 status 快照取 owner_identity；非法或缺省返回 undefined（不发送）。 */
export function gameModOwnerIdentity(status) {
  const value = status?.owner_identity;
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) return undefined;
  return value;
}

/** 终态 Banner：取消/部分写入/业务失败不用绿色成功。 */
export function gameModStatusTone({ active = false, checking = false, job = null, result = null } = {}) {
  if (active || checking) return 'info';
  const status = job?.status;
  const partial = Boolean(result?.partial);
  const failedBiz = result?.success === false;
  if (status === 'cancelled' || partial || (status === 'done' && failedBiz)) return 'warning';
  if (status === 'failed') return result?.written || partial ? 'warning' : 'error';
  if (status === 'done') return 'success';
  return 'info';
}
