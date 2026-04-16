import React from 'react';
import LogoMark from './LogoMark';

interface LoadingSpinnerProps {
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message = 'Loading…' }) => {
  return (
    <div
      className="flex items-center justify-center min-h-screen"
      style={{ background: 'var(--bg-base)' }}
    >
      <div className="text-center animate-fade-in">
        <div className="relative inline-flex mb-6">
          {/* Outer pulse ring */}
          <div
            className="absolute inset-0 rounded-2xl animate-ping"
            style={{ background: 'rgba(34,211,238,0.15)', animationDuration: '1.5s' }}
          />
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(145deg, #0d1117, #161b22)',
              border: '1px solid rgba(34,211,238,0.25)',
              boxShadow: '0 0 32px rgba(34,211,238,0.2)',
            }}
          >
            <LogoMark size={32} />
          </div>
        </div>
        <p className="text-sm text-gray-500 font-medium">{message}</p>
      </div>
    </div>
  );
};