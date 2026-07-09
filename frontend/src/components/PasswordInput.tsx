import React, { useState } from 'react';
import { AuthInput } from './AuthInput';

interface PasswordInputProps extends React.ComponentProps<typeof AuthInput> {
  // We can add additional props like showStrength, showVisibilityToggle if needed.
  showStrength?: boolean;
  showVisibilityToggle?: boolean;
}

export const PasswordInput: React.FC<PasswordInputProps> = ({ 
  showStrength = false, 
  showVisibilityToggle = true, 
  ...props 
}) => {
  const [isVisible, setIsVisible] = useState(false);

  const toggleVisibility = () => {
    setIsVisible(!isVisible);
  };

  const rightIcon = showVisibilityToggle ? (
    <button
      type="button"
      onClick={toggleVisibility}
      aria-label={isVisible ? 'Hide password' : 'Show password'}
      title={isVisible ? 'Hide password' : 'Show password'}
      className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded transition-colors duration-200 cursor-pointer flex items-center justify-center"
      style={{ minWidth: '44px', minHeight: '44px' }}
    >
      <div className="relative w-5 h-5 flex items-center justify-center">
        {/* Eye Icon (Shows when hidden, click to reveal) */}
        <svg
          className={`absolute transition-opacity duration-300 ${isVisible ? 'opacity-0' : 'opacity-100'}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
          width="20" height="20"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
        
        {/* Eye-Off Icon (Shows when visible, click to hide) */}
        <svg
          className={`absolute transition-opacity duration-300 ${isVisible ? 'opacity-100' : 'opacity-0'}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
          width="20" height="20"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
        </svg>
      </div>
    </button>
  ) : props.rightIcon;

  return (
    <div className="w-full">
      <AuthInput
        {...props}
        type={isVisible ? 'text' : 'password'}
        rightIcon={rightIcon}
      />
      {showStrength && (
        <div className="mt-2 text-xs text-gray-500 flex justify-between">
          <span>Password strength indicator</span>
          {/* Implement strength logic if needed */}
        </div>
      )}
    </div>
  );
};
