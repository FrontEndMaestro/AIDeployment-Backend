import React from 'react';

interface ButtonProps {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  loading?: boolean;
  className?: string;
  onClick?: () => void;
  type?: 'button' | 'submit' | 'reset';
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  className = '',
  onClick,
  type = 'button',
}) => {
  const baseStyles =
    'font-semibold rounded-xl transition-all flex items-center justify-center gap-2 whitespace-nowrap select-none';

  const variants = {
    primary:
      'bg-gradient-to-r from-cyan-500 to-blue-600 text-white ' +
      'shadow-[0_0_20px_rgba(34,211,238,0.25),0_4px_12px_rgba(0,0,0,0.3)] ' +
      'hover:shadow-[0_0_32px_rgba(34,211,238,0.4),0_6px_20px_rgba(0,0,0,0.4)] ' +
      'hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]',
    secondary:
      'bg-[rgba(22,27,34,0.8)] border border-white/10 text-gray-200 ' +
      'hover:bg-[rgba(30,37,46,0.9)] hover:border-white/20 hover:-translate-y-0.5',
    danger:
      'bg-rose-500/10 border border-rose-500/30 text-rose-400 ' +
      'hover:bg-rose-500/20 hover:border-rose-500/50 hover:-translate-y-0.5',
    ghost:
      'text-gray-400 hover:text-white hover:bg-white/5 border border-transparent hover:border-white/10',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-5 py-2.5 text-sm',
    lg: 'px-7 py-3.5 text-base',
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none ${className}`}
    >
      {loading && (
        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
      )}
      {children}
    </button>
  );
};