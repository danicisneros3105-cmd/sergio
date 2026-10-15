// A page's icon: a line icon in the text colour (no emoji, no colour).
import {
  Archive, Bell, Book, Bookmark, Brain, Briefcase, Building2, Calendar, Camera, Check, Clock, Code2, Coffee, Dumbbell,
  FileText, Film, Flag, FlaskConical, Folder, Gift, Globe, GraduationCap, Heart, Home, Key, Leaf, Lightbulb, List, Lock,
  Mail, Map, MessageSquare, Moon, Music, NotebookPen, Palette, Phone, Plane, Receipt, Rocket, ShoppingCart, Star, Sun,
  Target, TrendingUp, Users, Wallet, Wrench, Zap,
} from 'lucide-react';
import { iconName } from '../../lib/workspace/notion';

export const ICON_SET: Record<string, typeof FileText> = {
  file: FileText, note: NotebookPen, book: Book, bookmark: Bookmark, folder: Folder, archive: Archive, calendar: Calendar,
  clock: Clock, check: Check, list: List, target: Target, flag: Flag, star: Star, bolt: Zap, bulb: Lightbulb, brain: Brain,
  rocket: Rocket, briefcase: Briefcase, home: Home, building: Building2, cart: ShoppingCart, wallet: Wallet,
  chart: TrendingUp, receipt: Receipt, plane: Plane, map: Map, coffee: Coffee, heart: Heart, dumbbell: Dumbbell,
  music: Music, camera: Camera, film: Film, palette: Palette, code: Code2, wrench: Wrench, flask: FlaskConical,
  graduation: GraduationCap, users: Users, chat: MessageSquare, mail: Mail, phone: Phone, lock: Lock, key: Key,
  globe: Globe, leaf: Leaf, sun: Sun, moon: Moon, gift: Gift, bell: Bell,
};

export function NxIcon({ icon, size = 16, fallback = true }: { icon?: string | null; size?: number; fallback?: boolean }) {
  const Icon = ICON_SET[iconName(icon)] ?? (fallback ? FileText : null);
  return Icon ? <Icon size={size} strokeWidth={size > 40 ? 1.2 : 1.6} aria-hidden="true" /> : null;
}
