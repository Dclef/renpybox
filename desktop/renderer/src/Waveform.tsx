/**
 * 吞吐波形 —— 对齐 widget/WaveformWidget.py（115 行）的绘制口径。
 *
 * 原控件的关键参数与算法：
 *   QFont("Consolas", 8) → 列宽按字符宽度 8px 计；set_matrix_size(50, 20)
 *   → max_width = 50*8 = 400、max_height = 20*8 = 160、setFixedHeight(160)
 *   定时器 500ms（refresh_rate = 2）；history 超过 matrix_width 时 pop(0)，无新值时重复最后一个采样
 *   归一化：平坦（max == min）时 history[0] == 0 → 全 0，否则全 1；否则 (v - min) / (max - min)
 *   绘制：峰值 > 0 → accent alpha 218，gap = min(2, max(0.5, slot*0.24))，
 *         bar_height = max(2, (height-4)*value)，圆角 1.5
 *         峰值为 0 → 只画底部 y = height-1 的一条基线，accent alpha 56
 *
 * 采样节拍由父组件持有（进度事件何时到达由引擎决定），本组件只负责按上面的口径画。
 * 用 preserveAspectRatio="none" 复刻 Qt 侧 Expanding 的水平拉伸。
 */

export function Waveform(props: { points: number[]; columns?: number; height?: number }) {
  const { points, columns = 50, height = 160 } = props;
  const slot = 8;
  const width = columns * slot;
  const gap = Math.min(2, Math.max(0.5, slot * 0.24));
  const barWidth = Math.max(1, slot - gap);

  const history = points.slice(-columns);
  const min = history.length > 0 ? Math.min(...history) : 0;
  const max = history.length > 0 ? Math.max(...history) : 0;
  const hasThroughput = max > 0;

  const values =
    max === min
      ? history.map(() => (history[0] === 0 ? 0 : 1))
      : history.map((point) => (point - min) / (max - min));

  return (
    <svg
      className="waveform"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ height }}
      role="img"
      aria-label="实时吞吐波形"
    >
      {hasThroughput ? (
        values.map((value, index) => {
          const barHeight = Math.max(2, (height - 4) * value);
          return (
            <rect
              key={index}
              className="waveform-bar"
              x={index * slot + gap / 2}
              y={height - barHeight}
              width={barWidth}
              height={barHeight}
              rx={1.5}
              ry={1.5}
            />
          );
        })
      ) : (
        <rect className="waveform-baseline" x={0} y={height - 1} width={width} height={1} />
      )}
    </svg>
  );
}
