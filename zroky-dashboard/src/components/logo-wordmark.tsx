import React from "react";
import { Logo } from "./logo";

interface LogoWordmarkProps {
  size?: number;
  color?: string;
  layout?: "inline" | "stacked";
  showText?: boolean;
  className?: string;
  textClassName?: string;
}

export const LogoWordmark: React.FC<LogoWordmarkProps> = ({
  size = 32,
  color = "currentColor",
  layout = "inline",
  showText = false,
  className,
  textClassName,
}) => {
  const isInline = layout === "inline";

  return (
    <div
      className={className}
      style={{
        display: "flex",
        flexDirection: isInline ? "row" : "column",
        alignItems: "center",
        gap: isInline ? size * 0.375 : size * 0.25,
      }}
    >
      <Logo size={size} color={color} />
      {showText && (
        <span
          className={textClassName}
          style={{
            fontFamily: "var(--font-manrope), system-ui, sans-serif",
            fontSize: isInline ? size * 0.8125 : size * 0.6875,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            lineHeight: 1,
            color,
            whiteSpace: "nowrap",
          }}
        >
          Zroky
        </span>
      )}
    </div>
  );
};

export default LogoWordmark;
