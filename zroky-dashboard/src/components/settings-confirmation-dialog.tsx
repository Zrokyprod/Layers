"use client";

import { type ReactNode, useEffect, useRef } from "react";

type SettingsConfirmationDialogProps = {
  ariaLabel: string;
  busy?: boolean;
  children: ReactNode;
  onClose: () => void;
};

export function SettingsConfirmationDialog({
  ariaLabel,
  busy = false,
  children,
  onClose,
}: SettingsConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");

    const buttons = dialog.querySelectorAll<HTMLElement>("button:not([disabled])");
    buttons.item(buttons.length - 1)?.focus();

    return () => {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      window.setTimeout(() => returnFocus?.focus(), 0);
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="panel keys-revoke-modal settings-confirmation-dialog"
      aria-label={ariaLabel}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      {children}
    </dialog>
  );
}
