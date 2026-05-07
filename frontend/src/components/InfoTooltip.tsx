import { useState } from 'react';

interface InfoTooltipProps {
  content: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export function InfoTooltip({ content, position = 'top' }: InfoTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div
      className="info-tooltip-container"
      style={{ position: 'relative', display: 'inline-block', marginLeft: '6px' }}
    >
      <button
        className="info-icon-btn"
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsVisible(!isVisible);
        }}
        aria-label="More information"
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'help',
          padding: '2px 6px',
          fontSize: '14px',
          color: '#64748b',
          transition: 'color 0.2s',
        }}
        onMouseOver={(e) => (e.currentTarget.style.color = '#3b82f6')}
        onMouseOut={(e) => (e.currentTarget.style.color = '#64748b')}
      >
        ℹ️
      </button>

      {isVisible && (
        <div
          className={`tooltip-content tooltip-${position}`}
          style={{
            position: 'absolute',
            zIndex: 9999,
            background: '#1e293b',
            color: '#e2e8f0',
            padding: '10px 14px',
            borderRadius: '8px',
            fontSize: '13px',
            lineHeight: '1.5',
            maxWidth: '280px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            border: '1px solid #334155',
            whiteSpace: 'normal',
            wordWrap: 'break-word',
            ...(position === 'top' && { bottom: '100%', left: '50%', transform: 'translateX(-50%)', marginBottom: '8px' }),
            ...(position === 'bottom' && { top: '100%', left: '50%', transform: 'translateX(-50%)', marginTop: '8px' }),
            ...(position === 'left' && { right: '100%', top: '50%', transform: 'translateY(-50%)', marginRight: '8px' }),
            ...(position === 'right' && { left: '100%', top: '50%', transform: 'translateY(-50%)', marginLeft: '8px' }),
          }}
        >
          {content}
        </div>
      )}
    </div>
  );
}
