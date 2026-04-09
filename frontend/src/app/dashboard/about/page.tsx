'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  Info, ShieldCheck, LineChart,
  CheckCircle2, ArrowRight,
} from 'lucide-react';

const capabilityItems = [
  'Run as an operations workspace with dashboards, alerts, analytics, and operator-facing control workflows.',
  'Store official-source event records with source links, timestamps, and raw evidence preserved for audit.',
  'Compute repeatable risk scores from stored event data instead of hand-written labels.',
  'Generate alerts and watchlist matches that operators can inspect field by field.',
  'Show missing fields honestly instead of filling gaps with guessed data.',
];

const benefitItems = [
  'Faster review of emerging operational risks from records that can be traced back to stored source evidence.',
  'One place to inspect alerts, analytics, provenance, and pipeline activity without switching tools.',
  'Traceable scoring instead of unexplained severity claims.',
  'Higher client trust through visible verification, timestamps, clear missing-field handling, and step-by-step automation visibility.',
];

const automationItems = [
  'Background workers check configured official feeds automatically.',
  'Verified records are stored with source links, timestamps, and raw evidence preserved.',
  'Risk scores, analytics, alerts, and watchlist matches are recomputed from those stored records.',
  'Embedded global map views were removed so clients focus on the actual stored evidence instead of a confusing visual layer.',
];

export default function AboutPage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">About ORVANTA</h1>
          <p className="page-subtitle">Clear product overview and trust guidance for operations workspace usage.</p>
        </div>
      </div>

      <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 20, fontWeight: 800, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Info size={20} style={{ color: 'var(--accent-indigo)' }} />
          What This Software Is
        </h2>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.8, maxWidth: 920 }}>
          ORVANTA is an operations platform for organizations that need a single operational view of events,
          alerts, risk scores, analytics, and client-facing controls. It turns stored incoming event data into structured dashboards, calculated
          risk insights, and reviewable workflows while keeping source provenance visible. Only official-source verified records
          are surfaced in the main views, and raw technical payloads are preserved for audit instead of being replaced with invented summaries.
        </p>
      </motion.div>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.08 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <ShieldCheck size={18} style={{ color: 'var(--accent-emerald)' }} />
            What It Can Do
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {capabilityItems.map((item) => (
              <div key={item} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <CheckCircle2 size={16} style={{ color: 'var(--accent-emerald)', marginTop: 2, flexShrink: 0 }} />
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{item}</p>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.16 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <LineChart size={18} style={{ color: 'var(--accent-cyan)' }} />
            Benefits
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {benefitItems.map((item) => (
              <div key={item} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <CheckCircle2 size={16} style={{ color: 'var(--accent-cyan)', marginTop: 2, flexShrink: 0 }} />
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{item}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <div style={{ marginBottom: 24 }}>
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Info size={18} style={{ color: 'var(--accent-indigo)' }} />
            How To Verify Results
          </h3>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 12 }}>
            The platform is designed to surface real stored records and computed outputs, but client trust still depends on review.
            Use the source URL, source published/seen time, event date, stored time, and exact coordinates together before treating a result
            as fully confirmed. Analytics trend lines are grouped from real stored event timeline dates, and raw JSON is available as supporting
            payload context, not as a replacement for source verification.
          </p>
          <Link href="/dashboard/manage" className="btn btn-ghost" style={{ width: '100%' }}>
            Open Manage Controls
            <ArrowRight size={16} />
          </Link>
        </motion.div>
      </div>

      <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.36 }} style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>How Automation Works</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {automationItems.map((item, index) => (
            <div key={item} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: 'rgba(6, 182, 212, 0.14)',
                  color: 'var(--accent-cyan)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {index + 1}
              </div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{item}</p>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Recommended Navigation</h3>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          Use the links below to move directly into the right workflow depending on what the client wants to inspect.
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Link href="/dashboard" className="btn btn-ghost">Dashboard</Link>
          <Link href="/dashboard/analytics" className="btn btn-ghost">Analytics</Link>
          <Link href="/dashboard/alerts" className="btn btn-ghost">Alerts</Link>
          <Link href="/dashboard/manage" className="btn btn-primary">Manage</Link>
        </div>
      </motion.div>
    </div>
  );
}
