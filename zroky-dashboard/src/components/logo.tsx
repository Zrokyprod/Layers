import React from "react";

interface LogoProps {
  size?: number;
  color?: string;
  className?: string;
}

export const Logo: React.FC<LogoProps> = ({
  size = 40,
  color = "currentColor",
  className,
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Zroky logo"
      role="img"
    >
      {/* Top bar */}
      <line
        x1="50"
        y1="36"
        x2="76"
        y2="51"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
      />
      {/* Upper diagonal */}
      <line
        x1="76"
        y1="51"
        x2="64"
        y2="59"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
      />
      {/* Lower diagonal */}
      <line
        x1="56"
        y1="63"
        x2="44"
        y2="70"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
      />
      {/* Bottom bar */}
      <line
        x1="44"
        y1="70"
        x2="70"
        y2="84"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
      />

      {/* Hexagonal node — top-left */}
      <path
        d="M50 31 L53.46 33.5 L53.46 38.5 L50 41 L46.54 38.5 L46.54 33.5 Z"
        fill={color}
      />
      {/* Hexagonal node — bottom-right */}
      <path
        d="M70 79 L73.46 81.5 L73.46 86.5 L70 89 L66.54 86.5 L66.54 81.5 Z"
        fill={color}
      />

      {/* Gap triangle */}
      <path d="M60 54 L65 63 L55 63 Z" fill={color} />
    </svg>
  );
};

export default Logo;
