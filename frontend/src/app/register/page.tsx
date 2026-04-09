'use client';

import { useState } from 'react';
import Link from 'next/link';
import { authAPI } from '@/lib/api';
import { motion } from 'framer-motion';
import { Globe, UserPlus } from 'lucide-react';
import GoogleSignInButton from '@/components/GoogleSignInButton';
import { getSupabaseClient, isSupabaseConfigured } from '@/lib/supabase';

export default function RegisterPage() {
  const [form, setForm] = useState({ email: '', username: '', password: '', full_name: '', org_name: '' });
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const signInWithGoogle = async (credential: string) => {
    setError('');
    try {
      const res = await authAPI.loginWithGoogle({ credential });
      localStorage.setItem('warops_token', res.data.access_token);
      localStorage.setItem('warops_user', JSON.stringify(res.data));
      window.location.href = '/dashboard';
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Google sign-in failed');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      if (!isSupabaseConfigured()) {
        setError('Supabase auth is not configured. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.');
        return;
      }

      const payload = {
        ...form,
        email: form.email.trim().toLowerCase(),
        username: form.username.trim(),
        full_name: form.full_name.trim(),
        org_name: form.org_name.trim(),
      };

      const supabase = getSupabaseClient();
      const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
        email: payload.email,
        password: payload.password,
        options: {
          data: {
            full_name: payload.full_name || undefined,
          },
        },
      });

      if (signUpError) {
        setError(signUpError.message || 'Registration failed');
        return;
      }

      const accessToken = signUpData.session?.access_token;
      if (!accessToken) {
        setMessage('Verification email sent. Please verify your email, then sign in.');
        return;
      }

      const res = await authAPI.loginWithSupabase({
        access_token: accessToken,
        username: payload.username,
        full_name: payload.full_name || undefined,
        org_name: payload.org_name,
      });

      localStorage.setItem('warops_token', res.data.access_token);
      localStorage.setItem('warops_user', JSON.stringify(res.data));
      window.location.href = '/dashboard';
    } catch (err: any) {
      if (!err.response) {
        setError('Cannot reach API server. Please ensure backend/nginx is running.');
        return;
      }
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail[0]?.msg : 'Registration failed') || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const update = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [field]: e.target.value });

  return (
    <div className="auth-container">
      <motion.div
        className="auth-card"
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div style={{ textAlign: 'center', marginBottom: 8 }}>
          <Globe size={40} style={{ color: '#6366f1' }} />
        </div>
        <h1>Create Account</h1>
        <p>Start monitoring geopolitical risks</p>

        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <GoogleSignInButton
            text="signup_with"
            onCredential={signInWithGoogle}
            onError={(message) => setError(message)}
          />
        </div>
        <p style={{ marginBottom: 20, fontSize: 12 }}>or continue with email registration</p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Full Name</label>
            <input className="input" placeholder="John Doe" value={form.full_name} onChange={update('full_name')} />
          </div>

          <div className="form-group">
            <label>Email</label>
            <input type="email" className="input" placeholder="you@company.com" value={form.email} onChange={update('email')} required />
          </div>

          <div className="form-group">
            <label>Username</label>
            <input className="input" placeholder="johndoe" value={form.username} onChange={update('username')} required />
          </div>

          <div className="form-group">
            <label>Organization Name</label>
            <input className="input" placeholder="Your Company" value={form.org_name} onChange={update('org_name')} required />
          </div>

          <div className="form-group">
            <label>Password</label>
            <input type="password" className="input" placeholder="Min 8 characters" value={form.password} onChange={update('password')} required />
          </div>

          {message && <div className="form-success">{message}</div>}
          {error && <div className="form-error">{error}</div>}

          <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%', marginTop: 16 }} disabled={loading}>
            {loading ? 'Creating...' : <><UserPlus size={18} /> Create Account</>}
          </button>
        </form>

        <p style={{ marginTop: 24, fontSize: 13, textAlign: 'center', color: 'var(--text-muted)' }}>
          Already have an account?{' '}
          <Link href="/login" style={{ color: 'var(--accent-indigo)' }}>Sign in</Link>
        </p>
      </motion.div>
    </div>
  );
}
