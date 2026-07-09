import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { authGoogleLogin } from '../api';

const GOOGLE_LOGO = (
  <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#4285F4" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
    <path fill="#34A853" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
    <path fill="#FBBC05" d="M10.54 28.59A14.5 14.5 0 0 1 9.5 24c0-1.59.28-3.14.76-4.59l-7.98-6.19A23.99 23.99 0 0 0 0 24c0 3.77.87 7.35 2.56 10.56l7.98-5.97z" />
    <path fill="#EA4335" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 5.97C6.51 42.62 14.62 48 48 48z" />
  </svg>
);

const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const CLIENT_ID_MISSING = !clientId;

if (CLIENT_ID_MISSING) {
  console.warn(
    '[GoogleSignInButton] VITE_GOOGLE_CLIENT_ID is not set. ' +
    'Google Sign-In is disabled. To enable, set VITE_GOOGLE_CLIENT_ID in frontend/.env.development\n' +
    'Create an OAuth 2.0 Web Client ID at https://console.cloud.google.com/apis/credentials'
  );
} else {
  console.info('[GoogleSignInButton] Loaded VITE_GOOGLE_CLIENT_ID:', clientId.slice(0, 8) + '...');
}

const spinner = (
  <svg className="animate-spin h-5 w-5 text-gray-500 dark:text-gray-400" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
  </svg>
);

const buttonClass =
  'w-full h-[50px] flex items-center justify-center gap-3 px-4 rounded-lg border border-gray-300 dark:border-gray-600 ' +
  'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 font-medium text-sm ' +
  'hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ' +
  'dark:focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors';

export const GoogleSignInButton: React.FC = () => {
  if (CLIENT_ID_MISSING) {
    return <GoogleSignInUnavailable />;
  }
  return <GoogleSignInActive />;
};

const GoogleSignInActive: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [error, setError] = useState('');
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => { mountedRef.current = false; };
  }, []);

  const handleGoogleSignIn = useCallback(() => {
    setIsAuthenticating(true);
    setError('');
    console.info('[GoogleSignInButton] Opening Google OAuth popup...');

    const { google } = window as any;
    if (!google?.accounts?.oauth2) {
      console.error('[GoogleSignInButton] Google Identity Services SDK not loaded');
      if (mountedRef.current) {
        setError('Google Identity Services failed to load. Please refresh and try again.');
        setIsAuthenticating(false);
      }
      return;
    }

    const tokenClient = google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: 'openid email profile',
      callback: async (response: any) => {
        console.info('[GoogleSignInButton] callback fired', {
          hasError: !!response.error,
          hasIdToken: !!response.id_token,
          hasAccessToken: !!response.access_token,
        });

        if (!mountedRef.current) {
          console.info('[GoogleSignInButton] callback ignored (unmounted)');
          return;
        }

        if (response.error) {
          setIsAuthenticating(false);
          if (response.error === 'popup_closed_by_user' || response.error === 'access_denied') {
            console.info('[GoogleSignInButton] User cancelled the sign-in popup');
            setError('Google sign-in was cancelled.');
          } else {
            console.error('[GoogleSignInButton] Google OAuth error:', response.error, response.error_description);
            setError(`Google sign-in failed (${response.error_description || response.error}). Please try again.`);
          }
          return;
        }

        if (!response.id_token) {
          console.error('[GoogleSignInButton] No id_token in Google response', response);
          setIsAuthenticating(false);
          setError('No authentication token received from Google.');
          return;
        }

        console.info('[GoogleSignInButton] Sending token to backend...');
        try {
          const data = await authGoogleLogin(response.id_token);
          if (!mountedRef.current) return;
          console.info('[GoogleSignInButton] Backend login successful', { user: data.user });
          login(data.user);
          const from = location.state?.from?.pathname || '/';
          console.info('[GoogleSignInButton] Redirecting to:', from);
          navigate(from, { replace: true });
        } catch (err: any) {
          if (!mountedRef.current) return;
          console.error('[GoogleSignInButton] Backend login failed:', err.message);
          setError(err.message || 'Google sign-in failed. Please try again.');
        } finally {
          if (mountedRef.current) {
            setIsAuthenticating(false);
          }
        }
      },
    });

    tokenClient.requestAccessToken();
  }, [navigate, location, login]);

  return (
    <div className="w-full">
      <button
        type="button"
        onClick={handleGoogleSignIn}
        disabled={isAuthenticating}
        aria-label="Continue with Google"
        className={buttonClass}
      >
        {isAuthenticating ? (
          <>
            {spinner}
            <span>Authenticating...</span>
          </>
        ) : (
          <>
            {GOOGLE_LOGO}
            <span>Continue with Google</span>
          </>
        )}
      </button>
      {error && (
        <p className="mt-2 text-sm text-red-500 dark:text-red-400 text-center" role="alert">{error}</p>
      )}
    </div>
  );
};

const GoogleSignInUnavailable: React.FC = () => (
  <div className="w-full">
    <button
      type="button"
      disabled
      aria-label="Continue with Google"
      className={buttonClass}
    >
      {GOOGLE_LOGO}
      <span>Continue with Google</span>
    </button>
    <p className="mt-2 text-sm text-yellow-600 dark:text-yellow-400 text-center" role="status">
      Google Sign-In is currently unavailable.
    </p>
  </div>
);
