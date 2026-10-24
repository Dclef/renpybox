/** 剧情蓝图错误态判定的类型声明（供渲染端 import 使用）。 */

export const BLUEPRINT_API_MISSING_KEYS: {
  readonly title: 'story_blueprint_api_missing_title';
  readonly body: 'story_blueprint_api_missing_body';
};

/** 引导卡：后端里没有剧情蓝图接口（旧后端 / 没重启）。 */
export type BlueprintApiMissingView = {
  kind: 'api_missing';
  titleKey: 'story_blueprint_api_missing_title';
  bodyKey: 'story_blueprint_api_missing_body';
  /** 固定为空：英文 `Not Found` 不再显示。 */
  message: '';
};

/** 其它错误：原样显示后端/浏览器给的报错文案。 */
export type BlueprintOtherErrorView = {
  kind: 'other';
  titleKey: null;
  bodyKey: null;
  message: string;
};

export type BlueprintErrorView = BlueprintApiMissingView | BlueprintOtherErrorView;

export function isBlueprintApiMissing(error: unknown): boolean;
export function resolveBlueprintErrorView(error: unknown): BlueprintErrorView | null;
