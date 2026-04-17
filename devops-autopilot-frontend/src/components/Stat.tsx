import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface StatProps {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  trend?: 'up' | 'down';
  trendValue?: string;
  color?: string;
}

export const Stat: React.FC<StatProps> = ({ label, value, icon, trend, trendValue, color = '#22d3ee' }) => {
  return (
    <div
      className="glass-card p-5 stat-card"
      style={{ borderColor: `${color}22` }}
    >
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">{label}</p>
        {icon && (
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: `${color}12`, border: `1px solid ${color}25` }}
          >
            <span style={{ color }}>{icon}</span>
          </div>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-white tabular-nums">{value}</span>
        {trend && trendValue && (
          <span
            className="inline-flex items-center gap-0.5 text-xs font-semibold"
            style={{ color: trend === 'up' ? '#10b981' : '#f43f5e' }}
          >
            {trend === 'up'
              ? <TrendingUp size={12} />
              : <TrendingDown size={12} />
            }
            {trendValue}
          </span>
        )}
      </div>
    </div>
  );
};