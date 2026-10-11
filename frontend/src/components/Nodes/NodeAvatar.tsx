import { useId, useMemo } from 'react';

/** Original procedural character: bounded geometry, no textures or model requests. */
export function NodeAvatar({ colour, fur = 0.65, species = 'lumen', size = 110 }:
  { colour: string; fur?: number; species?: string; size?: number }) {
  const id = useId().replace(/:/g, '');
  const shape = useMemo(() => {
    const points: Array<{x: number; y: number}> = [];
    for (let i = 0; i < 180; i++) {
      const a = i * Math.PI * 2 / 180;
      const tuft = (Math.sin(i * 2.39996) * 0.5 + 0.5) * Math.max(0, Math.min(fur, 1)) * 5;
      const x = 60 + Math.cos(a) * (35 + tuft);
      const y = 65 + Math.sin(a) * (32 + tuft);
      points.push({x, y});
    }
    const midpoint = (a: typeof points[number], b: typeof points[number]) => `${((a.x + b.x) / 2).toFixed(2)},${((a.y + b.y) / 2).toFixed(2)}`;
    return `M${midpoint(points[179], points[0])} ` + points.map((p, i) => `Q${p.x.toFixed(2)},${p.y.toFixed(2)} ${midpoint(p, points[(i + 1) % 180])}`).join(' ') + ' Z';
  }, [fur]);
  return <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden="true">
    <defs><radialGradient id={id}><stop offset="0" stopColor="#fff" stopOpacity=".55" />
      <stop offset=".4" stopColor={colour} /><stop offset="1" stopColor={colour} stopOpacity=".85" /></radialGradient></defs>
    <ellipse cx="60" cy="106" rx="30" ry="5" fill="currentColor" opacity=".09" />
    <path d={species === 'nival' ? 'M30 48 L29 17 L48 40 M73 40 L93 17 L92 50' : 'M28 48 Q17 22 40 29 L49 42 M73 42 Q103 20 95 49'}
      fill={colour} stroke={colour} strokeWidth="3" strokeLinejoin="round" />
    <path d={shape} fill={`url(#${id})`} />
    <ellipse cx="60" cy="73" rx="23" ry="18" fill="#fff3df" opacity=".78" />
    <ellipse cx="47" cy="65" rx="3.6" ry={species === 'bruma' ? 2.3 : 5} fill="#292431" />
    <ellipse cx="73" cy="65" rx="3.6" ry={species === 'bruma' ? 2.3 : 5} fill="#292431" />
    <path d="M55 77 Q60 82 65 77" fill="none" stroke="#54404a" strokeWidth="2" strokeLinecap="round" />
    <ellipse cx="36" cy="94" rx="9" ry="6" fill={colour} /><ellipse cx="84" cy="94" rx="9" ry="6" fill={colour} />
  </svg>;
}
