import type { UpdateState } from './types';

export interface WebUpdateUi {
  status: string;
  statusText: string;
  progress: number;
  offerUpdate: boolean;
  /** 桌面迁移：引导打开发布页，不走自动下载/安装 */
  offerMigration: boolean;
  showProgress: boolean;
  showCancel: boolean;
  showInstall: boolean;
  tag: string;
}

export function displayVersion(tag: string): string;
export function formatMegabytes(size: number): string;

export interface UpdateDelivery {
  /** delta：文件级增量包；full：完整安装包；空字符串：尚未确定 */
  kind: 'delta' | 'full' | '';
  /** 相比完整安装包省下的字节数，非增量为 0 */
  savedBytes: number;
  /** 本次实际要下载的字节数 */
  modeSize: number;
  /** 完整安装包的字节数 */
  fullSize: number;
}

export function describeUpdateDelivery(update: {
  mode?: string;
  deltaAssetSize?: number;
  assetSize?: number;
} | null | undefined): UpdateDelivery;

export function resolveWebUpdateUi(update: Partial<UpdateState> | null | undefined, checking?: boolean): WebUpdateUi;
