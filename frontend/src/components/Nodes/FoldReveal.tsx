import { useEffect, useState } from 'react';
import { NodeAvatar } from './NodeAvatar';
import './nodes.css';

export function FoldReveal({ colour, species, trigger }: { colour: string; species: string; trigger: string }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), 700);
    return () => window.clearTimeout(timer);
  }, [trigger]);
  if (!visible) return null;
  return <div className="node-fold-overlay" aria-hidden="true" key={trigger}>
    <div className="node-fold-left"><NodeAvatar colour={colour} species={species} size={180} /></div>
    <div className="node-fold-right"><NodeAvatar colour={colour} species={species} size={180} /></div>
  </div>;
}
