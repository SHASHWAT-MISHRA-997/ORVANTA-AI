import Link from 'next/link';
import { Globe } from 'lucide-react';

import HomeRedirect from '@/components/HomeRedirect';

export default function Home() {
  return (
    <div className="auth-container">
      <HomeRedirect />
      <div className="auth-card" style={{ textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 14 }}>
          <Globe size={42} style={{ color: 'var(--accent-indigo)' }} />
        </div>
        <h1 className="brand-wordmark brand-wordmark-auth">ORVANTA</h1>
        <p>Opening your workspace...</p>
        <div
          style={{
            marginBottom: 20,
            color: 'var(--text-secondary)',
            fontSize: 14,
          }}
        >
          Redirecting to login or dashboard.
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 10, flexWrap: 'wrap' }}>
          <Link href="/login" className="btn btn-primary">
            Open Login
          </Link>
          <Link href="/dashboard" className="btn btn-ghost">
            Open Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
