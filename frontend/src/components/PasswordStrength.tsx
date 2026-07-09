import React, { useMemo } from 'react';

interface PasswordStrengthProps {
  password: string;
  email: string;
}

const TOTAL_SEGMENTS = 5;

const LEVELS = [
  { label: 'Weak', fillColor: 'bg-red-500', textColor: 'text-red-600 dark:text-red-400' },
  { label: 'Fair', fillColor: 'bg-orange-500', textColor: 'text-orange-600 dark:text-orange-400' },
  { label: 'Good', fillColor: 'bg-yellow-500', textColor: 'text-yellow-600 dark:text-yellow-400' },
  { label: 'Strong', fillColor: 'bg-green-500', textColor: 'text-green-600 dark:text-green-400' },
  { label: 'Excellent', fillColor: 'bg-emerald-500', textColor: 'text-emerald-600 dark:text-emerald-400' },
];

const EMPTY_SEGMENT = 'bg-gray-200 dark:bg-gray-600';

function getMetCount(password: string): number {
  let count = 0;
  if (password.length >= 8) count += 1;
  if (/[A-Z]/.test(password)) count += 1;
  if (/[a-z]/.test(password)) count += 1;
  if (/\d/.test(password)) count += 1;
  if (/[@$!%*?&]/.test(password)) count += 1;
  return count;
}

export const PasswordStrength: React.FC<PasswordStrengthProps> = React.memo(({ password }) => {
  const met = useMemo(() => getMetCount(password), [password]);

  return (
    <div className="mt-3 space-y-2" role="group" aria-label="Password strength">
      <div
        className="flex gap-[3px] h-1.5"
        role="progressbar"
        aria-valuenow={met}
        aria-valuemin={0}
        aria-valuemax={TOTAL_SEGMENTS}
        aria-label={met > 0 ? `Password strength: ${LEVELS[met - 1].label}` : 'Password strength'}
      >
        {Array.from({ length: TOTAL_SEGMENTS }).map((_, i) => (
          <div
            key={i}
            className={`flex-1 rounded-full transition-all duration-300 ease-out ${
              i < met ? LEVELS[met - 1].fillColor : EMPTY_SEGMENT
            }`}
          />
        ))}
      </div>

      {met > 0 && (
        <p className={`text-xs font-semibold tracking-wide transition-all duration-300 ${LEVELS[met - 1].textColor}`}>
          {LEVELS[met - 1].label}
        </p>
      )}
    </div>
  );
});

PasswordStrength.displayName = 'PasswordStrength';
