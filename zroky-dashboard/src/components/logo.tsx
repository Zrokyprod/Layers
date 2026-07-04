import React from "react";

interface LogoProps {
  size?: number;
  /** Kept for API compatibility; the brand logo is a fixed-color asset. */
  color?: string;
  className?: string;
}

export const Logo: React.FC<LogoProps> = ({ size = 40, className }) => {
  const width = Math.round(size * 2.96);

  return (
    // eslint-disable-next-line @next/next/no-img-element -- Shared logo can render inside client-only and print-only surfaces.
    <img
      src="/zroky-brand.png"
      width={width}
      height={size}
      className={className}
      alt="Zroky"
      style={{ objectFit: "contain", display: "block" }}
    />
  );
};

export default Logo;
