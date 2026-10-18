import { NodeCritter, type CritterShape } from './NodeCritter';

/** Fold previews use the same ink character as the Node itself. */
export function NodeAvatar({ colour, species = 'lumen', size = 110 }: { colour: string; fur?: number; species?: string; size?: number }) {
  const shape: CritterShape = species === 'nival' ? 'dalmatian' : species === 'bruma' ? 'glove' : species === 'lumen' ? 'orb' : 'rhino';
  return <NodeCritter look={{ color: colour, shape, eyes: 'dots', accessory: 'none' }} size={size} />;
}
