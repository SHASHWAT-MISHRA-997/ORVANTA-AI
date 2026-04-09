'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LayoutDashboard, AlertTriangle, BarChart3,
  LogOut, Globe, Info, Menu, X,
  MapPinned, SlidersHorizontal,
} from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import AssistantWidget from '@/components/AssistantWidget';

const navItems = [
  { href: '/dashboard/about', label: 'About', icon: Info },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/dashboard/events', label: 'Events', icon: MapPinned },
  { href: '/dashboard/alerts', label: 'Alerts', icon: AlertTriangle },
  { href: '/dashboard/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/dashboard/manage', label: 'Manage', icon: SlidersHorizontal },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [orgName, setOrgName] = useState('');
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  useEffect(() => {
    const userData = localStorage.getItem('warops_user');
    if (userData) {
      try {
        const user = JSON.parse(userData);
        setOrgName(user.organization?.name || 'ORVANTA');
      } catch {
        setOrgName('ORVANTA');
      }
    } else {
      setOrgName('ORVANTA');
    }
  }, []);

  useEffect(() => {
    setIsMobileNavOpen(false);
  }, [pathname]);

  const handleLogout = () => {
    localStorage.removeItem('warops_token');
    localStorage.removeItem('warops_user');
    window.location.href = '/login';
  };

  const renderNav = () => (
    <>
      <nav className="sidebar-nav">
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`nav-item${pathname === href ? ' active' : ''}`}
          >
            <Icon size={18} />
            {label}
          </Link>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-org-row">
          <span className="sidebar-org-name">{orgName}</span>
          <ThemeToggle />
        </div>

        <button
          onClick={handleLogout}
          className="nav-item"
          style={{ width: '100%', border: 'none', background: 'transparent' }}
        >
          <LogOut size={18} />
          Sign Out
        </button>
        <div className="sidebar-credit">
          Made by{' '}
          <a
            href="https://www.linkedin.com/in/sm980/"
            target="_blank"
            rel="noopener noreferrer"
          >
            SHASHWAT MISHRA
          </a>
        </div>
      </div>
    </>
  );

  return (
    <div>
      <aside className="sidebar">
        <div className="sidebar-logo">
          <Globe size={28} style={{ color: '#6366f1' }} />
          <h1 className="brand-wordmark">ORVANTA</h1>
        </div>
        {renderNav()}
      </aside>

      <header className="mobile-header">
        <div className="mobile-header-brand">
          <Globe size={24} style={{ color: '#6366f1' }} />
          <div>
            <strong className="brand-wordmark">ORVANTA</strong>
            <span>{orgName}</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ThemeToggle />
          <button
            className="mobile-menu-button"
            onClick={() => setIsMobileNavOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>
        </div>
      </header>

      <AnimatePresence>
        {isMobileNavOpen && (
          <motion.div
            className="mobile-nav-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsMobileNavOpen(false)}
          >
            <motion.aside
              className="mobile-nav-panel"
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ type: 'spring', stiffness: 280, damping: 28 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mobile-nav-header">
                <div className="sidebar-logo" style={{ marginBottom: 0, padding: 0 }}>
                  <Globe size={24} style={{ color: '#6366f1' }} />
                  <h1 className="brand-wordmark" style={{ fontSize: 18 }}>ORVANTA</h1>
                </div>
                <button
                  className="mobile-menu-button"
                  onClick={() => setIsMobileNavOpen(false)}
                  aria-label="Close navigation"
                >
                  <X size={20} />
                </button>
              </div>
              {renderNav()}
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="main-content">
        {children}
      </main>
      <AssistantWidget />
    </div>
  );
}
