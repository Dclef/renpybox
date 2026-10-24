/**
 * 剧情蓝图「接口缺失」判定：把后端错误翻译成一句人话，或者原样保留。
 *
 * 背景：桌面端打开剧情蓝图页时，出现的是英文 `Not Found`。原因是那个 sidecar
 * 进程是旧代码启动的，根本没有 `api/routes/story_blueprint.py` 里的路由；
 * 汉化者不是程序员，看不懂 `Not Found`，也不知道要去重启 / 升级。
 *
 * 所以这里只做一件事：判断这次失败是不是「后端没有这些接口」。
 * - 是 → 给一张中文引导卡（文案走 i18n，见 BLUEPRINT_API_MISSING_KEYS）；
 * - 不是 → 什么都不动，让页面继续把后端原文显示出来，真实原因不能被盖掉。
 */

/** 引导卡用的 i18n 键；页面据此取文案，测试据此断言。 */
export const BLUEPRINT_API_MISSING_KEYS = Object.freeze({
  title: 'story_blueprint_api_missing_title',
  body: 'story_blueprint_api_missing_body',
});

/** 后端路由不存在时 FastAPI 的默认 detail，以及 request() 的兜底文案里的状态码。 */
const MISSING_API_HINTS = [/\bnot\s*found\b/i, /\b404\b/];

/** 取出错误上的 HTTP 状态码；不是 ApiError 形状就返回 0。 */
function statusOf(error) {
  const status = error && typeof error === 'object' ? error.status : null;
  const value = Number(status);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

/** 取出可显示的报错文案；对象优先用 message，其余按字符串处理。 */
function messageOf(error) {
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && typeof error.message === 'string') return error.message;
  return String(error ?? '').trim();
}

/**
 * 这次失败是不是「后端里没有剧情蓝图的接口」。
 *
 * 两条判据（任一命中即可）：
 * 1. HTTP 404 —— 路由不存在时后端就是这个状态；
 * 2. 报错文案里出现 `Not Found` 或 `404` —— 前端只保留了 message 的地方也能判出来。
 *
 * @param {unknown} error 抛出来的错误（ApiError / Error / 字符串 / 任意值）。
 * @returns {boolean}
 */
export function isBlueprintApiMissing(error) {
  if (statusOf(error) === 404) return true;
  const message = messageOf(error);
  return MISSING_API_HINTS.some((pattern) => pattern.test(message));
}

/**
 * 错误 → 视图判定。
 *
 * - `null`：没有错误，页面照常画数据。
 * - `api_missing`：换成引导卡，`message` 为空 —— 英文 `Not Found` 不再上屏。
 * - `other`：保持原有 Banner 行为，`message` 是后端/浏览器给的原文。
 *
 * @param {unknown} error
 * @returns {null | { kind: 'api_missing' | 'other', titleKey: string | null,
 *   bodyKey: string | null, message: string }}
 */
export function resolveBlueprintErrorView(error) {
  const hasError = error !== null && error !== undefined && error !== '' && error !== false;
  if (!hasError) return null;

  if (isBlueprintApiMissing(error)) {
    return {
      kind: 'api_missing',
      titleKey: BLUEPRINT_API_MISSING_KEYS.title,
      bodyKey: BLUEPRINT_API_MISSING_KEYS.body,
      message: '',
    };
  }

  const message = messageOf(error);
  return {
    kind: 'other',
    titleKey: null,
    bodyKey: null,
    // 兜底：后端连 detail 都没有时也别给个空 Banner。
    message: message || '请求失败',
  };
}
