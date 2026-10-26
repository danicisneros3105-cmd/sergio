// A permission Sergio (or a Node) asks for, in plain words: what it wants
// to do, «Sí» / «No», and the exact commands folded away for whoever wants
// to read them.

import { Check, ShieldQuestion, X } from 'lucide-react';
import { categoryLabel, type PlainApproval } from '../../lib/plainReply';

export function ApprovalCard({
  approval,
  onAnswer,
}: {
  approval: PlainApproval;
  /** Without it the card only informs (the answer comes from elsewhere). */
  onAnswer?: (yes: boolean) => void;
}) {
  return (
    <div className="approval-card" role="group" aria-label="Necesita tu permiso">
      <div className="approval-head">
        <ShieldQuestion size={16} aria-hidden />
        <span>{categoryLabel(approval.category)}</span>
      </div>
      <p className="approval-what">{approval.summary}</p>
      {approval.details && (
        <details className="approval-details">
          <summary>Ver detalles</summary>
          <pre>{approval.details}</pre>
        </details>
      )}
      {onAnswer && (
        <div className="approval-actions">
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => onAnswer(false)}>
            <X size={14} /> No
          </button>
          <button type="button" className="paper-button" onClick={() => onAnswer(true)}>
            <Check size={14} /> Sí, hazlo
          </button>
        </div>
      )}
    </div>
  );
}
