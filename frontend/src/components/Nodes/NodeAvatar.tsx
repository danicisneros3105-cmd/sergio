import { NodeCritter, type CritterShape } from './NodeCritter';

/** Fold previews use the same friendly character renderer as the Node itself. */
export function NodeAvatar({ colour, species = 'lumen', size = 110 }:
  { colour: string; fur?: number; species?: string; size?: number }) {
  const shape: CritterShape = species === 'nival' ? 'bear' : species === 'bruma' ? 'blob' : 'bean';
  return <NodeCritter look={{ color: colour, shape, eyes: 'dots', accessory: 'none' }} size={size} />;
}
