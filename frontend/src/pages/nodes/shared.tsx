import { useEffect, useState } from 'react';
import { NodeCritter } from '../../components/Nodes/NodeCritter';
import { listConnectors } from '../../lib/connectors-api';
import type { ConnectorInfo } from '../../types/connectors';
import { SHAPE_ES, type Avatar, type Catalog, type SergioNode, type TeamMember } from '../../lib/nodes';

const FALLBACK_AVATAR: Avatar = { shape: 'rhino', color: '#9fd3ff', accessory: 'none', eyes: 'sleepy' };

export function look(node?: Pick<SergioNode, 'avatar'> | null): Avatar {
  return node?.avatar || FALLBACK_AVATAR;
}

/** The team member a Node is (Rihno, Manchas, Hous, Tennessee), if it is one. */
export function memberOf(node: Pick<SergioNode, 'team'>, catalog: Catalog | null): TeamMember | undefined {
  return node.team ? catalog?.team?.find((m) => m.key === node.team) : undefined;
}

/** A Node can be stopped mid-action only while it is doing something. */
export function isActive(node: Pick<SergioNode, 'busy' | 'status'>): boolean {
  return node.busy || node.status === 'working' || node.status === 'waiting_approval';
}

export function useConnectors() {
  const [apps, setApps] = useState<ConnectorInfo[]>([]);
  useEffect(() => {
    listConnectors()
      .then(setApps)
      .catch(() => setApps([]));
  }, []);
  return apps;
}

// -- a Node's character: one of the four, never designed ------------------------------

export function CharacterCard({ avatar, member }: { avatar: Avatar; member?: TeamMember }) {
  const name = member?.name || SHAPE_ES[avatar.shape] || 'Node';
  return (
    <div className="critter-card">
      <NodeCritter look={avatar} size={132} status="idle" label={name} />
      <b>{name}</b>
      {member && <span className="critter-card-role">{member.role}</span>}
      {member?.does && <span className="critter-card-does">{member.does}</span>}
    </div>
  );
}

export function ToneSelect({ value, onChange, catalog }: { value: string; onChange: (t: string) => void; catalog: Catalog | null }) {
  return (
    <div className="critter-chips" role="radiogroup" aria-label="Forma de hablar">
      {(catalog?.tones || []).map((t) => (
        <button key={t.key} type="button" role="radio" className="mac-chip" aria-checked={value === t.key} aria-pressed={value === t.key} title={t.label} onClick={() => onChange(t.key)}>
          {t.key[0].toUpperCase() + t.key.slice(1)}
        </button>
      ))}
    </div>
  );
}
