import { NavLink, useLocation, useNavigate } from 'react-router';
import {
  MessageSquare, Code, Image, Boxes, PenTool, Layers, Cpu,
  BarChart3, Wallet, Users, Settings, ChevronDown, Zap,
  Sparkles, Film, LayoutDashboard, Star, MonitorPlay, Bot,
  Palette, BookOpen, Wand2, Brain, Command, Monitor,
  Workflow, Boxes as Boxes3d, Shapes, Ruler, Building2,
  CircleDot, Eye, Pencil, ArrowUpRight, Lock, LogOut, User,
  ChevronRight, Gem, ImagePlus, Presentation, Wrench, QrCode,
  Megaphone, Globe, ScanLine, Send, Newspaper, Clock, Server,
  HardDrive, Shield, Globe2, Volume2, CircleDollarSign, Hammer,
  Flame, TrendingUp, Grid3X3, FileCode, GitFork, Repeat, Stethoscope,
  Plug, Puzzle, Cloud, Code2, CloudCog, Package, ArrowLeftRight,
  Network, Infinity, Table, CreditCard, BadgeCheck, HelpCircle,
  Search, Plus, Compass, FolderOpen, ShoppingBag, Share2, Type,
  Music, Clapperboard, Target,
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

function classNames(...c: Array<string | false | undefined>) {
  return c.filter(Boolean).join(' ');
}

const ITEMS: Array<{
  to: string;
  label: string;
  icon: React.ElementType;
  children?: Array<{ to: string; label: string; icon: React.ElementType; desc?: string }>;
}> = [
  {
    to: '/chat',
    label: 'Chat IA',
    icon: MessageSquare,
    children: [
      { to: '/chat', label: 'Chat', icon: MessageSquare, desc: 'Conversacion con IA' },
      { to: '/chat/memoria', label: 'Memoria', icon: Brain, desc: 'Recuerdos y contexto' },
    ],
  },
  {
    to: '/editor',
    label: 'Editor',
    icon: Film,
    children: [
      { to: '/editor', label: 'Video Studio', icon: Clapperboard, desc: 'Editor de video con IA' },
      { to: '/creator/imagen', label: 'Studio Imagen', icon: ImagePlus, desc: 'Diseno e imagen' },
    ],
  },
  {
    to: '/creator',
    label: 'Studio',
    icon: Palette,
    children: [
      { to: '/creator/imagen', label: 'Imagen', icon: ImagePlus, desc: 'Diseno grafico e ilustracion' },
      { to: '/creator/modelado', label: '3D', icon: Boxes3d, desc: 'Modelado 3D' },
      { to: '/creator/arquitectura', label: 'Arquitectura', icon: Building2, desc: 'Diseno arquitectonico' },
      { to: '/creator/diseno', label: 'UI/UX', icon: LayoutDashboard, desc: 'Interfaces de usuario' },
      { to: '/creator/prototipos', label: 'Prototipos', icon: PenTool, desc: 'Prototipos interactivos' },
      { to: '/creator/codigo', label: 'Codigo', icon: Code, desc: 'Programacion' },
      { to: '/creator/bolsa', label: 'Trading', icon: TrendingUp, desc: 'Analisis de mercado' },
    ],
  },
  {
    to: '/galeria',
    label: 'Galeria',
    icon: Image,
  },
];

const MORE_ITEMS = [
  { to: '/planes', label: 'Planes', icon: Star },
  { to: '/uso', label: 'Uso', icon: BarChart3 },
  { to: '/ayuda', label: 'Ayuda', icon: HelpCircle },
  { to: '/about', label: 'Acerca', icon: Info },
];

function Info(props: any) { return <BookOpen {...props} />; }

export function Toolbar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenu(null);
        setMoreOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const isActive = (to: string) => {
    if (to === '/chat') return location.pathname.startsWith('/chat');
    if (to === '/editor') return location.pathname === '/editor' || location.pathname === '/creator' || location.pathname.startsWith('/creator/');
    if (to === '/creator') return location.pathname.startsWith('/creator');
    return location.pathname === to;
  };

  const allNavItems = [
    ...ITEMS.flatMap((i) => i.children ?? [{ to: i.to, label: i.label, icon: i.icon }]),
    ...MORE_ITEMS,
  ];

  const filtered = searchQuery.trim()
    ? allNavItems.filter((i) => i.label.toLowerCase().includes(searchQuery.toLowerCase()))
    : [];

  return (
    <aside className="toolbar">
      <nav ref={menuRef}>
        {ITEMS.map((item) => {
          const active = isActive(item.to);
          return (
            <div key={item.to} className="toolbar-item-wrap">
              <NavLink
                to={item.to}
                className={classNames('toolbar-item', active && 'active')}
                onClick={() => { setOpenMenu(null); setMoreOpen(false); }}
                onMouseEnter={() => item.children && setOpenMenu(item.to)}
              >
                <item.icon size={20} strokeWidth={1.8} />
                <span>{item.label}</span>
                {item.children && <ChevronDown size={12} />}
              </NavLink>
              {item.children && openMenu === item.to && (
                <div className="toolbar-submenu" onMouseLeave={() => setOpenMenu(null)}>
                  {item.children.map((child) => (
                    <NavLink
                      key={child.to}
                      to={child.to}
                      className={({ isActive }) => classNames('toolbar-submenu-item', isActive && 'active')}
                      onClick={() => setOpenMenu(null)}
                    >
                      <child.icon size={14} />
                      <div>
                        <span>{child.label}</span>
                        {child.desc && <small>{child.desc}</small>}
                      </div>
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        <div className="toolbar-divider" />

        <button
          className={classNames('toolbar-item', moreOpen && 'active')}
          onClick={() => setMoreOpen((v) => !v)}
        >
          <Grid3X3 size={20} strokeWidth={1.8} />
          <span>Mas</span>
          <ChevronDown size={12} />
        </button>
        {moreOpen && (
          <div className="toolbar-submenu">
            {MORE_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => classNames('toolbar-submenu-item', isActive && 'active')}
                onClick={() => setMoreOpen(false)}
              >
                <item.icon size={14} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        )}
      </nav>
    </aside>
  );
}
