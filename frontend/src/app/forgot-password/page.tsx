'use client';

import { useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Mail } from 'lucide-react';
import { getSupabaseClient, isSupabaseConfigured } from '@/lib/supabase';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [resetLink, setResetLink] = useState('');
  const [inboxUrl, setInboxUrl] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setResetLink('');
    setInboxUrl('');
    setLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      if (!isSupabaseConfigured()) {
        setError('Supabase is not configured. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.');
        return;
      }

      const supabase = getSupabaseClient();
      const redirectTo = `${window.location.origin}/reset-password`;
      const { error: supabaseError } = await supabase.auth.resetPasswordForEmail(normalizedEmail, {
        redirectTo,
      });
      if (supabaseError) {
        setError(supabaseError.message || 'Unable to send reset email');
        return;
      }

      setMessage('If that email exists, password reset instructions have been sent.');
    } catch (err: any) {
      if (err.code === 'ECONNABORTED') {
        setError('Request timed out. Please try again.');
        return;
      }
      const detail = err.response?.data?.detail;
      const message = err.response?.data?.message;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (typeof message === 'string') {
        setError(message);
      } else if (!err.response) {
        setError('Cannot reach server. Please ensure backend is running.');
      } else {
        setError('Unable to process request');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <motion.div
        className="auth-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1>Forgot Password</h1>
        <p>Enter your email to receive reset instructions.</p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              className="input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          {message && <div className="form-success">{message}</div>}
          {resetLink && (
            <div className="form-success" style={{ marginTop: 12 }}>
              <a href={resetLink} style={{ color: 'var(--accent-indigo)', fontWeight: 600 }}>
                Open reset link
              </a>
            </div>
          )}
          {inboxUrl && (
            <div className="form-success" style={{ marginTop: 12 }}>
              <a
                href={inboxUrl}
                target="_blank"
                rel="noreferrer"
                style={{ color: 'var(--accent-indigo)', fontWeight: 600 }}
              >
                Open local inbox
              </a>
            </div>
          )}
          {error && <div className="form-error">{error}</div>}

          <button
            type="submit"
            className="btn btn-primary btn-lg"
            style={{ width: '100%', marginTop: 16 }}
            disabled={loading}
          >
            {loading ? 'Sending...' : <><Mail size={18} /> Send Reset Link</>}
          </button>
        </form>

        <p style={{ marginTop: 24, fontSize: 13, textAlign: 'center', color: 'var(--text-muted)' }}>
          Back to{' '}
          <Link href="/login" style={{ color: 'var(--accent-indigo)' }}>Sign In</Link>
        </p>
      </motion.div>
    </div>
  );
}
