/**
 * 进度环 —— 对齐 qfluentwidgets ProgressRing 在翻译页的用法
 * （frontend/TranslationPage.py:1186-1192）：
 *   setRange(0, 10000) / setTextVisible(True) / setStrokeWidth(8) / setFixedSize(122, 122)
 *   文字格式 translation_page_progress_empty = "0.0%\n0 / 0"（两行居中的百分比 + 行数）
 *
 * 环本身用 SVG 画：轨道整圈 + 值弧线按 stroke-dasharray 截取，
 * 线帽 round、从 12 点方向顺时针起算（等价于 Qt 的 -90° 起始角）。
 */

export function ProgressRing(props: {
  /** 当前值，defaultMax 是 10000 以对齐 Qt 侧的 range */
  value: number;
  max?: number;
  size?: number;
  stroke?: number;
  /** 环内文字，逐行居中显示 */
  lines: string[];
}) {
  const { value, max = 10000, size = 122, stroke = 8, lines } = props;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const ratio = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  const dash = circumference * ratio;
  const center = size / 2;

  return (
    <div className="progress-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          className="progress-ring-track"
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={stroke}
        />
        <circle
          className="progress-ring-value"
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference - dash}`}
          transform={`rotate(-90 ${center} ${center})`}
        />
      </svg>
      <div className="progress-ring-text">
        {lines.map((line, index) => (
          // 行内容本身就是文案，用序号做 key 即可
          <span key={index}>{line}</span>
        ))}
      </div>
    </div>
  );
}
