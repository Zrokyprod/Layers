// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

export function newCallId(): string {
  const randomUUID = globalThis.crypto?.randomUUID;
  if (typeof randomUUID === "function") {
    return randomUUID.call(globalThis.crypto);
  }

  const random = Math.random().toString(36).slice(2, 12);
  return `js_${Date.now().toString(36)}_${random}`;
}

export function newEventId(callId: string): string {
  return `${callId}:capture`;
}
