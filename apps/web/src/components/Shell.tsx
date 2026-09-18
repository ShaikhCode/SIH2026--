import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Activity, BookOpen, GraduationCap, LayoutDashboard, LogOut, Menu, Users, WifiOff, X } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { LANGS } from '../types';

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const isAdmin = user?.account_role === 'admin';

  useEffect(() => {
    const close = () => setOpen(false);
    window.addEventListener('resize', close);
    return () => window.removeEventListener('resize', close);
  }, []);

  const links = isAdmin
    ? [
        { to: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
        { to: '/groups', label: 'Classrooms', Icon: Users },
        { to: '/offline', label: 'Offline Center', Icon: WifiOff },
        { to: '/diagnostics', label: 'Diagnostics', Icon: Activity },
      ]
    : [
        { to: '/student', label: 'My Learning', Icon: GraduationCap },
        { to: '/groups', label: 'Join Classroom', Icon: Users },
        { to: '/offline', label: 'Offline Center', Icon: WifiOff },
      ];

  const signOut = async () => { await logout(); navigate('/login', { replace: true }); };

  return <div className="app-shell">
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="side-brand">
        <div className="brand-mark">भा</div>
        <div className="side-brand-copy"><strong>BhashaSaathi</strong><span>Translate the classroom, not just the words.</span></div>
        <button className="mobile-close" onClick={() => setOpen(false)} aria-label="Close navigation"><X size={18} /></button>
      </div>
      <div className="role-badge">{isAdmin ? 'EDUCATOR' : 'LEARNER'}</div>
      <nav className="side-nav">
        {links.map(({ to, label, Icon }) => <NavLink key={to} to={to} onClick={() => setOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={18} /><span>{label}</span></NavLink>)}
      </nav>
      <div className="side-bottom">
        <div className="user-mini"><div className="avatar">{user?.name?.slice(0, 1).toUpperCase()}</div><div><strong>{user?.name}</strong><span>{user ? LANGS[user.preferred_language]?.native : ''}</span></div></div>
        <button className="logout-btn" onClick={signOut}><LogOut size={16} /> Sign out</button>
      </div>
    </aside>
    {open && <button className="scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <main className="main">
      <div className="mobile-topbar"><button className="menu-btn" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu size={21} /></button><div className="mobile-brand"><div className="brand-mark small">भा</div><strong>BhashaSaathi</strong></div></div>
      {children}
    </main>
  </div>;
}

export function Page({ eyebrow, title, subtitle, actions, children }: { eyebrow?: string; title: string; subtitle?: string; actions?: ReactNode; children: ReactNode }) {
  return <div className="page"><header className="page-head"><div className="page-heading"><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{actions && <div className="head-actions">{actions}</div>}</header>{children}</div>;
}

export function Breadcrumbs({ items }: { items: Array<{ label: string; href?: string }> }) {
  return <div className="breadcrumbs">{items.map((item, index) => <span key={`${item.label}-${index}`}>{item.href ? <a href={item.href}>{item.label}</a> : item.label}{index < items.length - 1 && <b>›</b>}</span>)}</div>;
}

export function SectionTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="section-title"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}
