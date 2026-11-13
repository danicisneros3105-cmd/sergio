import { Link, useLocation } from 'react-router-dom';
import { Film, CreditCard } from 'lucide-react';
import './Toolbar.css';

export default function Toolbar() {
  const loc = useLocation();

  const links = [
    { to: '/editor', label: 'Studio', icon: Film },
    { to: '/plans', label: 'Planes', icon: CreditCard },
  ];

  return (
    <nav className="shell-toolbar">
      <Link to="/" className="shell-logo">SERGIO</Link>
      <div className="shell-links">
        {links.map(l => {
          const Icon = l.icon;
          const active = loc.pathname === l.to;
          return (
            <Link key={l.to} to={l.to} className={`shell-link ${active ? 'active' : ''}`}>
              <Icon size={14} />
              <span>{l.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
