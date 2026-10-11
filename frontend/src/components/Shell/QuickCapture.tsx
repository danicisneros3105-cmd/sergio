import { useLocation, useNavigate } from 'react-router';
import { Plus } from 'lucide-react';

// On phones: a small ink button to capture in one tap (hidden on capture
// itself and in the chat, where the composer already is).
export function QuickCapture() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  if (pathname === '/capturar' || pathname.startsWith('/chat')) return null;
  return (
    <button type="button" className="paper-fab md:hidden" aria-label="Captura rápida" onClick={() => navigate('/capturar')}>
      <Plus size={22} strokeWidth={1.5} />
    </button>
  );
}
