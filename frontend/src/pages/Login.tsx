import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { AuthLayout } from '../components/AuthLayout';
import { AuthInput } from '../components/AuthInput';
import { PasswordInput } from '../components/PasswordInput';
import { GoogleSignInButton } from '../components/GoogleSignInButton';
import { authLogin } from '../api';

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setServerError('Please enter both email and password.');
      return;
    }

    setIsSubmitting(true);
    setServerError('');
    try {
      const data = await authLogin({ email, password, remember_me: rememberMe });
      login(data.user);
      const from = location.state?.from?.pathname || "/";
      navigate(from, { replace: true });
    } catch (err: any) {
      setServerError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <div className="w-full">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold mb-1">Welcome back</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm">Please enter your details to sign in</p>
        </div>

        {location.state?.signupSuccess && (
          <div className="mb-4 p-3 rounded bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 text-sm border border-green-200 dark:border-green-800">
            Account created successfully. Please sign in.
          </div>
        )}

        {serverError && (
          <div className="mb-4 p-3 rounded bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800">
            {serverError}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          <AuthInput
            label="Email address"
            name="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <PasswordInput
            label="Password"
            name="password"
            placeholder="********"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="flex items-center justify-between pt-2">
            <label className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-300">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 bg-white dark:bg-gray-800"
              />
              <span>Remember for 30 days</span>
            </label>
          </div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 dark:bg-green-600 dark:hover:bg-green-700 text-white font-medium rounded-lg shadow-md hover:shadow-lg transition-all focus:outline-none disabled:opacity-50 mt-6"
          >
            {isSubmitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div className="relative my-6" role="separator" aria-orientation="horizontal">
          <div className="absolute inset-0 flex items-center" aria-hidden="true">
            <div className="w-full border-t border-gray-300 dark:border-gray-600" />
          </div>
          <div className="relative flex justify-center">
            <span className="px-4 text-sm text-gray-500 dark:text-gray-400 bg-white dark:bg-slate-950 rounded-full">
              OR
            </span>
          </div>
        </div>

        <GoogleSignInButton />

        <div className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
          Don't have an account?{' '}
          <button type="button" onClick={() => navigate('/signup')} className="text-blue-600 dark:text-green-500 hover:underline font-medium focus:outline-none">Sign up</button>
        </div>
      </div>
    </AuthLayout>
  );
};
