"use client";

import Link, { type LinkProps } from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

type DashboardButtonVariant = "primary" | "soft" | "ghost" | "danger";
type DashboardButtonSize = "sm" | "md" | "icon";

type DashboardButtonOwnProps = {
  children?: ReactNode;
  className?: string;
  icon?: ReactNode;
  iconPosition?: "left" | "right";
  loading?: boolean;
  size?: DashboardButtonSize;
  variant?: DashboardButtonVariant;
};

function buttonClassName({
  className,
  size = "md",
  variant = "soft",
}: Pick<DashboardButtonOwnProps, "className" | "size" | "variant">) {
  return cn("dashboard-button", `dashboard-button-${variant}`, `dashboard-button-${size}`, className);
}

function ButtonContent({
  children,
  icon,
  iconPosition = "left",
  loading,
}: Pick<DashboardButtonOwnProps, "children" | "icon" | "iconPosition" | "loading">) {
  const iconNode = icon ? (
    <span className="dashboard-button-glyph" aria-hidden="true">
      {icon}
    </span>
  ) : null;

  return (
    <>
      {loading ? <span className="dashboard-button-spinner" aria-hidden="true" /> : null}
      {iconPosition === "left" ? iconNode : null}
      {children ? <span className="dashboard-button-label">{children}</span> : null}
      {iconPosition === "right" ? iconNode : null}
    </>
  );
}

export type DashboardButtonProps = DashboardButtonOwnProps &
  ButtonHTMLAttributes<HTMLButtonElement>;

export function DashboardButton({
  children,
  className,
  disabled,
  icon,
  iconPosition,
  loading,
  size,
  type = "button",
  variant,
  ...props
}: DashboardButtonProps) {
  return (
    <button
      className={buttonClassName({ className, size, variant })}
      disabled={disabled || loading}
      type={type}
      {...props}
    >
      <ButtonContent icon={icon} iconPosition={iconPosition} loading={loading}>
        {children}
      </ButtonContent>
    </button>
  );
}

export type DashboardButtonLinkProps = DashboardButtonOwnProps &
  LinkProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, keyof LinkProps | "className" | "children"> & {
    "aria-disabled"?: boolean;
  };

export function DashboardButtonLink({
  children,
  className,
  icon,
  iconPosition,
  loading,
  size,
  variant,
  ...props
}: DashboardButtonLinkProps) {
  const ariaDisabled = props["aria-disabled"] || loading || undefined;

  return (
    <Link
      className={buttonClassName({ className, size, variant })}
      aria-disabled={ariaDisabled}
      {...props}
    >
      <ButtonContent icon={icon} iconPosition={iconPosition} loading={loading}>
        {children}
      </ButtonContent>
    </Link>
  );
}
