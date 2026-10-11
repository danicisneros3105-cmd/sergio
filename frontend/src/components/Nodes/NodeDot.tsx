import type { NodeStatus } from '../../lib/nodes';

// A Node's face: a soft floating dot with two eyes. It breathes while
// idle, pulses light blue while it works and wears a ring when it needs you.
export function NodeDot({
  color,
  status = 'idle',
  size = 40,
  label,
}: {
  color: string;
  status?: NodeStatus;
  size?: number;
  label?: string;
}) {
  const light = ['#ffffff', '#cfe9ff', '#9fd3ff'].includes(color.toLowerCase());
  return (
    <span
      className="node-dot"
      data-status={status}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={{ width: size, height: size, ['--dot' as string]: color, ['--eye' as string]: light ? '#000' : '#fff' }}
    >
      <span className="node-dot-body" />
      <span className="node-dot-eyes" style={{ gap: Math.max(3, size * 0.14) }}>
        <i style={{ width: Math.max(2.5, size * 0.09), height: Math.max(3.5, size * 0.14) }} />
        <i style={{ width: Math.max(2.5, size * 0.09), height: Math.max(3.5, size * 0.14) }} />
      </span>
    </span>
  );
}
