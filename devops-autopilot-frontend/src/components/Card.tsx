import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  glow?: boolean;
  style?: React.CSSProperties;
}

export const Card: React.FC<CardProps> = ({ children, className = '', glow = false, style }) => {
  return (
    <div
      className={`glass-card ${glow ? 'border-cyan-500/20 shadow-[0_0_32px_rgba(34,211,238,0.08)]' : ''} ${className}`}
      style={style}
    >
      {children}
    </div>
  );
};