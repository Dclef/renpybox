import { cpSync, existsSync, readdirSync } from 'node:fs';
import path from 'node:path';

/** 配置目录从 New UI 时代统一为 RenpyBox；旧目录仅在新目录为空时迁移一次。 */
export const APP_DATA_DIR_NAME = 'RenpyBox';
export const LEGACY_APP_DATA_DIR_NAME = 'RenpyBox-newUI';

/**
 * 旧版配置只做一次复制式迁移，不删除旧目录，失败也不阻塞启动。
 * fs 可注入，便于单测在临时目录里验证「不覆盖已有配置」。
 */
export function migrateLegacyProfile({
  appDataDir,
  logger = () => {},
  fs = { existsSync, readdirSync, cpSync },
} = {}) {
  if (!appDataDir) return { migrated: false, reason: 'no-app-data' };
  const legacy = path.join(appDataDir, LEGACY_APP_DATA_DIR_NAME);
  const target = path.join(appDataDir, APP_DATA_DIR_NAME);
  if (!fs.existsSync(legacy)) return { migrated: false, reason: 'absent' };

  let targetEmpty = true;
  if (fs.existsSync(target)) {
    try {
      targetEmpty = fs.readdirSync(target).length === 0;
    } catch {
      targetEmpty = false;
    }
  }
  if (!targetEmpty) return { migrated: false, reason: 'target-exists' };

  try {
    fs.cpSync(legacy, target, { recursive: true, force: false, errorOnExist: false });
    logger(`[profile] 已将旧版配置迁移到 ${target}`);
    return { migrated: true, from: legacy, to: target };
  } catch (error) {
    logger(`[profile] 旧版配置迁移失败，继续使用新目录：${error.message || error}`);
    return { migrated: false, reason: 'failed', error };
  }
}
