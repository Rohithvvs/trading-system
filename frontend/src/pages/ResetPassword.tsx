import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { PasswordInput } from '../components/PasswordInput';
import { PasswordStrength } from '../components/PasswordStrength';
import { resetPassword, toUserFacingApiMessage } from '../api';

export const ResetPassword: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);
  const [touched, setTouched] = useState(false);

  const passwordError = touched && password.length > 0 && password.length < 8 ? 'Password must be at least 8 characters' : '';
  const confirmError = confirmPassword && password !== confirmPassword ? 'Passwords do not match' : '';
  const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword;

  const isValid = useMemo(() => {
    return password.length >= 8 && confirmPassword === password && token.length > 0;
  }, [password, confirmPassword, token]);

  useEffect(() => {
    if (!token) {
      setServerError('Invalid reset link. No token provided.');
    }
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    setIsSubmitting(true);
    setServerError('');
    try {
      await resetPassword(token, password, confirmPassword);
      setIsSuccess(true);
      setTimeout(() => navigate('/login'), 3000);
    } catch (err: any) {
      setServerError(toUserFacingApiMessage(err, 'Password reset failed. The link may have expired.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <div className="w-full">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold mb-1">Reset Password</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm">
            Enter your new password below.
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
              Password updated successfully. Redirecting to login...
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <PasswordInput
              label="New Password"
              name="password"
              placeholder="********"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setTouched(true); }}
              error={passwordError ? passwordError : undefined}
            />

            {password && (
              <PasswordStrength password={password} email="" />
            )}

            <PasswordInput
              label="Confirm Password"
              name="confirmPassword"
              placeholder="********"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              error={confirmError ? `✗ ${confirmError}` : undefined}
              success={passwordsMatch ? '✓ Passwords match' : undefined}
            />

            <button
              type="submit"
              disabled={isSubmitting || !isValid}
              className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 dark:bg-green-600 dark:hover:bg-green-700 text-white font-medium rounded-lg shadow-md hover:shadow-lg transition-all focus:outline-none disabled:opacity-50 mt-2"
            >
              {isSubmitting ? 'Resetting...' : 'Reset Password'}
            </button>
          </form>
        )}
      </div>
    </AuthLayout>
  );
};
