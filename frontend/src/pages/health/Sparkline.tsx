// A small line of the last days, ink on paper; the healthy range as a light band.
export function Sparkline({
  points,
  width = 160,
  height = 40,
  low,
  high,
}: {
  points: Array<[string, number]>;
  width?: number;
  height?: number;
  low?: number | null;
  high?: number | null;
}) {
  if (points.length < 2) return <svg className="salud-spark" width={width} height={height} aria-hidden="true" />;
  const values = points.map((p) => p[1]);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (low != null) min = Math.min(min, low);
  if (high != null) max = Math.max(max, high);
  if (max === min) max = min + 1;
  const pad = 3;
  const x = (i: number) => pad + (i / (points.length - 1)) * (width - pad * 2);
  const y = (v: number) => height - pad - ((v - min) / (max - min)) * (height - pad * 2);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
  const bandTop = high != null ? y(high) : pad;
  const bandBottom = low != null ? y(low) : height - pad;
  const last = points[points.length - 1];
  return (
    <svg className="salud-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      {(low != null || high != null) && <rect x={0} y={bandTop} width={width} height={Math.max(0, bandBottom - bandTop)} className="salud-spark-band" />}
      <path d={d} fill="none" strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(points.length - 1)} cy={y(last[1])} r={2.6} />
    </svg>
  );
}

/** A full chart: one bar per day, the goal as a dashed line. */
export function DayBars({ points, goal, height = 160 }: { points: Array<[string, number]>; goal?: number | null; height?: number }) {
  if (!points.length) return null;
  const max = Math.max(...points.map((p) => p[1]), goal ?? 0) || 1;
  const w = 100 / points.length;
  return (
    <svg className="salud-bars" viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" role="img" aria-label="Valores por día">
      {points.map(([day, v], i) => {
        const h = (v / max) * (height - 4);
        return (
          <rect key={day} x={i * w + w * 0.15} y={height - h} width={w * 0.7} height={h}>
            <title>{`${day}: ${v}`}</title>
          </rect>
        );
      })}
      {goal != null && goal > 0 && <line x1={0} x2={100} y1={height - (goal / max) * (height - 4)} y2={height - (goal / max) * (height - 4)} className="salud-goal" />}
    </svg>
  );
}
