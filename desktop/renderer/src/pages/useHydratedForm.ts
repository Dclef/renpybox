/**
 * 表单水合生命周期：同一身份只从后端快照水合一次，用户改过表单后不再被轮询覆盖。
 * 轮询每次返回新对象引用（见 projectToolJob.tsx），页面不应仅凭引用变化重置本地输入。
 * 判定逻辑是纯函数 shouldHydrateForm，hook 只负责持有三个 ref 与身份变化时的重置。
 */
import { useRef } from 'react';

import { shouldHydrateAndroidForm } from '../androidBuildView.mjs';

export interface HydrateFlags {
  hydrated?: boolean;
  dirty?: boolean;
}

/** 纯判定：仅当同一身份下「未水合且用户未改过」才允许用后端值覆盖本地表单。 */
export const shouldHydrateForm = shouldHydrateAndroidForm;

export interface HydratedForm {
  /** 当前水合标记快照，供 mergeAndroidForm 等纯函数复用。 */
  flags(): HydrateFlags;
  /** 身份键是否相对上次调用发生了变化（调用方据此重置 hydrated/dirty）。 */
  identityChanged(): boolean;
  /** 是否应水合（内部已含 identityChanged 的重置逻辑）。 */
  shouldHydrate(): boolean;
  /** 标记用户改过表单，之后同身份内不再被后端快照覆盖。 */
  markDirty(): void;
  /** 标记已完成一次水合。 */
  markHydrated(): void;
}

/**
 * @param identityKey 身份键（如 statusPath + suite.identity）；变化时自动重置水合状态。
 */
export function useHydratedForm(identityKey: string): HydratedForm {
  const identityRef = useRef(identityKey);
  const hydratedRef = useRef(false);
  const dirtyRef = useRef(false);

  function resetIfIdentityChanged(): boolean {
    if (identityRef.current === identityKey) return false;
    identityRef.current = identityKey;
    hydratedRef.current = false;
    dirtyRef.current = false;
    return true;
  }

  return {
    flags(): HydrateFlags {
      return { hydrated: hydratedRef.current, dirty: dirtyRef.current };
    },
    identityChanged: resetIfIdentityChanged,
    shouldHydrate(): boolean {
      // 身份刚变化时本轮不水合：等新身份的 status 回包后再允许首次水合。
      if (resetIfIdentityChanged()) return false;
      return shouldHydrateAndroidForm({ hydrated: hydratedRef.current, dirty: dirtyRef.current });
    },
    markDirty(): void {
      dirtyRef.current = true;
    },
    markHydrated(): void {
      hydratedRef.current = true;
    },
  };
}
