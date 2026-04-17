import React from 'react';

interface ProgressBarProps {
  value: number;
  max?: number;
  label?: string;
  showPercentage?: boolean;
  color?: 'cyan' | 'green' | 'purple' | 'amber';
}

const GRADIENTS = {
  cyan:   'linear-gradient(90deg, #22d3ee, #3b82f6)',
  green:  'linear-gradient(90deg, #10b981, #22d3ee)',
  purple: 'linear-gradient(90deg, #a855f7, #3b82f6)',
  amber:  'linear-gradient(90deg, #f59e0b, #ef4444)',
};

export const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  max = 100,
  label,
  showPercentage = true,
  color = 'cyan',
}) => {
  const pct = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div>
      {(label || showPercentage) && (
        <div className="flex justify-between items-center mb-1.5">
          {label && <span className="text-xs font-medium text-gray-400">{label}</span>}
          {showPercentage && (
            <span className="text-xs font-semibold tabular-nums" style={{ color: GRADIENTS[color].includes('#22d3ee') ? '#22d3ee' : '#a855f7' }}>
              {Math.round(pct)}%
            </span>
          )}
        </div>
      )}
      <div
        className="w-full h-1.5 rounded-full overflow-hidden"
        style={{ background: 'rgba(255,255,255,0.06)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${pct}%`, background: GRADIENTS[color] }}
        />
      </div>
    </div>
  );
};