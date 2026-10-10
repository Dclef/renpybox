// 一键翻译页的纯展示逻辑：不依赖 React，便于 node:test 直接覆盖。

/**
 * 没有本次准备结果时，应用译文是否按增量处理。
 * 对齐 Qt5：只有当前翻译输出指向 <lang>_new 增量目录时才走增量合并，
 * 否则按全量覆盖主 TL，不能默认增量去合并可能过期的暂存目录。
 */
export function isIncrementalOutput(outputFolder) {
  return /_new[\\/]?$/.test(String(outputFolder ?? '').trim());
}
