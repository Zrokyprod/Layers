import React from "react";

interface LogoProps {
  size?: number;
  /** Kept for API compatibility; the brand logo is a fixed-color asset. */
  color?: string;
  className?: string;
}

export const Logo: React.FC<LogoProps> = ({ size = 40, className }) => {
  return (
    <img
      src="/zroky.logo.png"
      width={size}
      height={size}
      className={className}
      alt="Zroky logo"
      style={{ objectFit: "contain", display: "block" }}
    />
  );
};

export default Logo;
