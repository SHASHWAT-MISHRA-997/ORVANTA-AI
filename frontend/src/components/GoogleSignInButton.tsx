'use client';

import { useEffect, useRef, useState } from 'react';
import { Chrome } from 'lucide-react';

type GoogleButtonText = 'signin_with' | 'signup_with' | 'continue_with' | 'signin';

type GoogleSignInButtonProps = {
  text?: GoogleButtonText;
  onCredential: (credential: string) => void | Promise<void>;
  onError?: (message: string) => void;
};

export default function GoogleSignInButton({
  text = 'continue_with',
  onCredential,
  onError,
}: GoogleSignInButtonProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [unavailableReason, setUnavailableReason] = useState('');

  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) {
      setUnavailableReason('Google sign-in is not configured yet.');
      return;
    }

    const renderButton = () => {
      if (!window.google || !containerRef.current) {
        return;
      }

      const parentWidth = containerRef.current.parentElement?.clientWidth ?? 360;
      const buttonWidth = Math.max(220, Math.min(360, Math.floor(parentWidth)));

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response: { credential?: string }) => {
          if (response.credential) {
            void onCredential(response.credential);
            return;
          }
          onError?.('Google sign-in failed. Please try again.');
        },
      });

      containerRef.current.innerHTML = '';
      window.google.accounts.id.renderButton(containerRef.current, {
        theme: 'outline',
        size: 'large',
        shape: 'pill',
        text,
        width: buttonWidth,
      });
    };

    if (window.google) {
      renderButton();
      window.addEventListener('resize', renderButton);
      return () => window.removeEventListener('resize', renderButton);
    }

    const existingScript = document.getElementById('google-identity-script') as HTMLScriptElement | null;
    if (existingScript) {
      existingScript.addEventListener('load', renderButton);
      return () => existingScript.removeEventListener('load', renderButton);
    }

    const script = document.createElement('script');
    script.id = 'google-identity-script';
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = renderButton;
    script.onerror = () => onError?.('Unable to load Google Sign-In right now. Please retry.');
    document.head.appendChild(script);

    return () => {
      script.onload = null;
      script.onerror = null;
    };
  }, [onCredential, onError, text]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div ref={containerRef} style={{ width: '100%', maxWidth: 360 }} />
      {unavailableReason && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Chrome size={14} />
          {unavailableReason}
        </div>
      )}
    </div>
  );
}
