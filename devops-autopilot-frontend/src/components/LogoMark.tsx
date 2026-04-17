import React from 'react';

/**
 * DevOps AutoPilot logo mark — a stylized pipeline/circuit motif
 * that communicates infrastructure automation without being generic.
 */
interface LogoMarkProps {
  size?: number;
  className?: string;
}

export const LogoMark: React.FC<LogoMarkProps> = ({ size = 32, className = '' }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Outer circuit ring */}
    <circle cx="16" cy="16" r="14.5" stroke="url(#logo-ring)" strokeWidth="1.5" strokeDasharray="4 2.5" />

    {/* Pipeline flow arrows — left to right */}
    <path d="M4 16 H10" stroke="url(#logo-cyan)" strokeWidth="2" strokeLinecap="round" />
    <path d="M22 16 H28" stroke="url(#logo-cyan)" strokeWidth="2" strokeLinecap="round" />

    {/* Node squares */}
    <rect x="9.5" y="13.5" width="5" height="5" rx="1.5" fill="url(#logo-node1)" />
    <rect x="17.5" y="13.5" width="5" height="5" rx="1.5" fill="url(#logo-node2)" />

    {/* Central autopilot pip */}
    <circle cx="16" cy="16" r="2" fill="white" opacity="0.9" />

    {/* Vertical data rails */}
    <path d="M12 10 V7" stroke="#22d3ee" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />
    <path d="M20 10 V7" stroke="#a855f7" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />
    <path d="M12 22 V25" stroke="#22d3ee" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />
    <path d="M20 22 V25" stroke="#a855f7" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />

    <defs>
      <linearGradient id="logo-ring" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
        <stop stopColor="#22d3ee" stopOpacity="0.6" />
        <stop offset="1" stopColor="#a855f7" stopOpacity="0.4" />
      </linearGradient>
      <linearGradient id="logo-cyan" x1="0" y1="0" x2="32" y2="0" gradientUnits="userSpaceOnUse">
        <stop stopColor="#22d3ee" />
        <stop offset="1" stopColor="#3b82f6" />
      </linearGradient>
      <linearGradient id="logo-node1" x1="9.5" y1="13.5" x2="14.5" y2="18.5" gradientUnits="userSpaceOnUse">
        <stop stopColor="#22d3ee" />
        <stop offset="1" stopColor="#3b82f6" />
      </linearGradient>
      <linearGradient id="logo-node2" x1="17.5" y1="13.5" x2="22.5" y2="18.5" gradientUnits="userSpaceOnUse">
        <stop stopColor="#3b82f6" />
        <stop offset="1" stopColor="#a855f7" />
      </linearGradient>
    </defs>
  </svg>
);

export default LogoMark;
