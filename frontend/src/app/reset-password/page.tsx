'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { KeyRound } from 'lucide-react';
import { authAPI } from '@/lib/api';
import { getSupabaseClient, isSupabaseConfigured } from '@/lib/supabase';

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = useMemo(() => searchParams.get('token') || '', [searchParams]);
  const recoveryCode = useMemo(() => searchParams.get('code') || '', [searchParams]);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const prepareSupabaseRecoverySession = async () => {
      if (!isSupabaseConfigured()) {
        setSessionReady(true);
        return;
      }

      try {
        const supabase = getSupabaseClient();
        if (recoveryCode) {
          const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(recoveryCode);
          if (exchangeError && !cancelled) {
            setError(exchangeError.message || 'Invalid or expired recovery link.');
            setSessionReady(true);
            return;
          }
        }

        if (!cancelled) {
          setSessionReady(true);
        }
      } catch {
        if (!cancelled) {
          setSessionReady(true);
        }
      }
    };

    prepareSupabaseRecoverySession();

    return () => {
      cancelled = true;
    };
  }, [recoveryCode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');

    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      if (token) {
        const res = await authAPI.resetPassword({ token, new_password: password });
        setMessage(res.data?.message || 'Password reset successful.');
      } else {
        if (!isSupabaseConfigured()) {
          setError('Reset link is invalid for current setup.');
          return;
        }

        const supabase = getSupabaseClient();
        const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) {
          setError(sessionError.message || 'Unable to validate reset session.');
          return;
        }

        if (!sessionData.session) {
          setError('Reset session expired. Please request a new reset link.');
          return;
        }

        const { error: updateError } = await supabase.auth.updateUser({ password });
        if (updateError) {
          setError(updateError.message || 'Unable to reset password');
          return;
        }

        setMessage('Password reset successful. You can now log in.');
      }

      setPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Unable to reset password');
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
        <h1>Reset Password</h1>
        <p>Set a new password for your account.</p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>New Password</label>
            <input
              type="password"
              className="input"
              placeholder="Enter new password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label>Confirm Password</label>
            <input
              type="password"
              className="input"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>

          {message && <div className="form-success">{message}</div>}
          {error && <div className="form-error">{error}</div>}

          <button
            type="submit"
            className="btn btn-primary btn-lg"
            style={{ width: '100%', marginTop: 16 }}
            disabled={loading || (!token && !sessionReady)}
          >
            {loading ? 'Updating...' : <><KeyRound size={18} /> Update Password</>}
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

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="auth-container"><div className="auth-card"><p>Loading reset form...</p></div></div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
