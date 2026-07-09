import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { AuthInput } from '../components/AuthInput';
import { PasswordInput } from '../components/PasswordInput';
import { PasswordStrength } from '../components/PasswordStrength';
import { authSignup } from '../api';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const LOADING_MESSAGES = [
  'Creating account...',
  'Checking email availability...',
  'Encrypting password...',
  'Setting up secure account...',
];

function validateEmail(email: string): string {
  if (!email) return '';
  if (!EMAIL_RE.test(email)) return 'Invalid email address';
  return '';
}

function validateConfirmPassword(password: string, confirmPassword: string): string {
  if (!confirmPassword) return '';
  if (password !== confirmPassword) return 'Passwords do not match';
  return '';
}

export const Signup: React.FC = () => {
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');
  const [loadingIndex, setLoadingIndex] = useState(0);
  const loadingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const emailValidation = useMemo(() => {
    const err = validateEmail(formData.email);
    return {
      error: err,
      isValid: formData.email.length > 0 && !err,
      showIndicator: formData.email.length > 0,
    };
  }, [formData.email]);

  const confirmPasswordError = useMemo(
    () => validateConfirmPassword(formData.password, formData.confirmPassword),
    [formData.password, formData.confirmPassword]
  );

  const confirmPasswordMatch = formData.confirmPassword.length > 0 && !confirmPasswordError;

  const validateField = useCallback((name: string, value: string): string => {
    switch (name) {
      case 'fullName':
        return value.trim() ? '' : 'Full name is required';
      case 'email':
        return validateEmail(value);
      case 'password':
        return value.length >= 8 ? '' : 'Password must be at least 8 characters';
      case 'confirmPassword':
        return validateConfirmPassword(formData.password, value);
      default:
        return '';
    }
  }, [formData.password]);

  const validate = useCallback((): boolean => {
    const newErrors: Record<string, string> = {};
    const fields: (keyof typeof formData)[] = ['fullName', 'email', 'password', 'confirmPassword'];
    for (const field of fields) {
      const err = validateField(field, formData[field]);
      if (err) newErrors[field] = err;
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formData, validateField]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    if (name === 'password') {
      setFormData(prev => {
        const newConfirm = prev.confirmPassword && prev.password !== value ? '' : prev.confirmPassword;
        return { ...prev, password: value, confirmPassword: newConfirm };
      });
    }
  }, []);

  const handleBlur = useCallback((e: React.FocusEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setTouched(prev => ({ ...prev, [name]: true }));
    const err = validateField(name, value);
    setErrors(prev => {
      if (err) return { ...prev, [name]: err };
      const next = { ...prev };
      delete next[name];
      return next;
    });
  }, [validateField]);

  useEffect(() => {
    return () => {
      if (loadingTimerRef.current) clearInterval(loadingTimerRef.current);
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    setServerError('');
    loadingTimerRef.current = setInterval(() => {
      setLoadingIndex(prev => (prev + 1) % LOADING_MESSAGES.length);
    }, 1500);

    try {
      await authSignup({
        email: formData.email,
        full_name: formData.fullName,
        password: formData.password,
      });
      navigate('/login', { state: { signupSuccess: true } });
    } catch (err: any) {
      setServerError(err.message || 'Signup failed. Please try again.');
    } finally {
      if (loadingTimerRef.current) clearInterval(loadingTimerRef.current);
      setIsSubmitting(false);
    }
  };

  const isFormValid = useMemo(() => {
    return (
      formData.fullName.trim() &&
      emailValidation.isValid &&
      formData.password.length >= 8 &&
      formData.confirmPassword === formData.password
    );
  }, [formData, emailValidation]);

  return (
    <AuthLayout>
      <div className="w-full">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold mb-1">Create an Account</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm">Sign up to get started</p>
        </div>

        {serverError && (
          <div className="mb-4 p-3 rounded bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800">
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <AuthInput
            label="Full Name"
            name="fullName"
            type="text"
            placeholder="John Doe"
            value={formData.fullName}
            onChange={handleChange}
            onBlur={handleBlur}
            error={touched.fullName ? errors.fullName : undefined}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            }
          />

          <AuthInput
            label="Email address"
            name="email"
            type="email"
            placeholder="you@example.com"
            value={formData.email}
            onChange={handleChange}
            onBlur={handleBlur}
            error={emailValidation.showIndicator && emailValidation.error ? `✗ ${emailValidation.error}` : undefined}
            success={emailValidation.showIndicator && emailValidation.isValid ? '✓ Valid email' : undefined}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            }
          />

          <PasswordInput
            label="Password"
            name="password"
            placeholder="********"
            value={formData.password}
            onChange={handleChange}
            onBlur={handleBlur}
            error={touched.password ? errors.password : undefined}
            disabled={isSubmitting}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            }
          />

          {formData.password && (
            <PasswordStrength password={formData.password} email={formData.email} />
          )}

          <PasswordInput
            label="Confirm Password"
            name="confirmPassword"
            placeholder="********"
            value={formData.confirmPassword}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={isSubmitting}
            error={
              formData.confirmPassword && confirmPasswordError
                ? `✗ ${confirmPasswordError}`
                : undefined
            }
            success={
              formData.confirmPassword && confirmPasswordMatch
                ? '✓ Passwords match'
                : undefined
            }
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            }
          />

          <button
            type="submit"
            disabled={isSubmitting || !isFormValid}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 dark:bg-green-600 dark:hover:bg-green-700 text-white font-medium rounded-lg shadow-md hover:shadow-lg transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 dark:focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed mt-6"
          >
            {isSubmitting ? (
              <span className="flex items-center justify-center space-x-2">
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span>{LOADING_MESSAGES[loadingIndex]}</span>
              </span>
            ) : (
              'Sign Up'
            )}
          </button>
        </form>

        <div className="mt-8 text-center text-sm text-gray-500 dark:text-gray-400">
          Already have an account?{' '}
          <button
            type="button"
            onClick={() => navigate('/login')}
            className="text-blue-600 dark:text-green-500 hover:underline font-medium focus:outline-none"
          >
            Sign In
          </button>
        </div>
      </div>
    </AuthLayout>
  );
};
