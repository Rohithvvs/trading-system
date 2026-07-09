import React from 'react';
import { useTheme } from '../hooks/useTheme';

interface BullIllustrationProps {
  size?: number;
  className?: string;
}

export const BullIllustration: React.FC<BullIllustrationProps> = ({ size = 200, className = '' }) => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <div
      className={`relative overflow-hidden rounded-full transition-all duration-500 ${className}`}
      style={{
        width: size,
        height: size,
      }}
      aria-hidden="true"
    >
      <img
        src={isDark ? '/Dark_mode.png' : '/Light_mode.png'}
        alt=""
        className="w-full h-full select-none pointer-events-none"
        style={{ objectFit: 'cover', objectPosition: 'center' }}
        draggable={false}
      />
    </div>
  );
};
