import React from 'react';
import {
  LayoutDashboard,
  Package,
  Search,
  Network,
  PauseCircle,
  Truck,
  Boxes,
  Zap,
  BarChart3,
  ShoppingCart,
  LayoutGrid,
  ClipboardList,
  Pencil,
  Archive,
  FileBarChart2,
  Sparkles,
  Wrench,
  ShieldCheck,
  Settings,
  ChevronRight,
  Bell,
  User,
  Moon,
  Sun,
  Monitor,
  PanelLeft,
  X,
  Store,
  Eye,
  EyeOff,
  Lock,
  LogOut,
  ScanLine,
  KeyRound,
  Tags,
  Inbox,
  MessageCircle,
  Fingerprint,
} from 'lucide-react';

// Semantic name -> Lucide component. The call signature
// <Icon name="..." size={} className="" /> stays identical everywhere;
// only the rendering backend changed (hand-drawn SVG paths -> Lucide).
const ICONS = {
  dashboard: LayoutDashboard,
  inventory: Package,
  search: Search,
  network: Network,
  pause: PauseCircle,
  supplier: Truck,
  boxes: Boxes,
  bolt: Zap,
  chart: BarChart3,
  procurement: ShoppingCart,
  workspace: LayoutGrid,
  orders: ClipboardList,
  edit: Pencil,
  archive: Archive,
  reports: FileBarChart2,
  spark: Sparkles,
  tools: Wrench,
  admin: ShieldCheck,
  settings: Settings,
  chevron: ChevronRight,
  bell: Bell,
  user: User,
  moon: Moon,
  sun: Sun,
  monitor: Monitor,
  panel: PanelLeft,
  close: X,
  store: Store,
  eye: Eye,
  eyeOff: EyeOff,
  lock: Lock,
  logout: LogOut,
  scan: ScanLine,
  key: KeyRound,
  tags: Tags,
  inbox: Inbox,
  chat: MessageCircle,
  identity: Fingerprint,
};

export function Icon({ name, size = 16, className = '' }) {
  const Component = ICONS[name] || ICONS.dashboard;
  return (
    <Component
      className={`ntm-icon ${className}`.trim()}
      width={size}
      height={size}
      strokeWidth={1.75}
      color="currentColor"
      aria-hidden="true"
    />
  );
}
