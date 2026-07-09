import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { AuthInput } from '../components/AuthInput';
import { forgotPassword } from '../api';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const ForgotPassword: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);

  const emailError = email && !EMAIL_RE.test(email) ? 'Invalid email address' : '';
  const isValid = EMAIL_RE.test(email);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    setIsSubmitting(true);
    setServerError('');
    try {
      await forgotPassword(email);
      setIsSuccess(true);
    } catch (err: any) {
      setServerError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <div className="w-full">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold mb-1">Forgot Password?</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm">
            Enter your email and we'll send you a reset link.
          </p>
        </div>

        {serverError && (
          <div className="mb-4 p-3 rounded bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800">
            {serverError}
          </div>
        )}

        {isSuccess ? (
          <div className="text-center py-4 space-y-4">
            <div className="p-4 rounded bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 text-sm border border-green-200 dark:border-green-800">
              If an account exists, a password reset link has been sent.
            </div>
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="text-blue-600 dark:text-green-500 hover:underline font-medium text-sm focus:outline-none"
            >
              Back to Login
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <AuthInput
              label="Email address"
              name="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={emailError ? emailError : undefined}
            />
            <button
              type="submit"
              disabled={isSubmitting || !isValid}
              className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 dark:bg-green-600 dark:hover:bg-green-700 text-white font-medium rounded-lg shadow-md hover:shadow-lg transition-all focus:outline-none disabled:opacity-50 mt-2"
            >
              {isSubmitting ? 'Sending...' : 'Send Reset Link'}
            </button>
          </form>
        )}

        {!isSuccess && (
          <div className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="text-blue-600 dark:text-green-500 hover:underline font-medium focus:outline-none"
            >
              Back to Login
            </button>
          </div>
        )}
      </div>
    </AuthLayout>
  );
};
