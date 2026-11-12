import { useEffect, useRef } from "react";

/**
 * Keep a form's state in the browser while the user is still filling it in (M9).
 *
 * The draft survives switching tabs or windows, navigating elsewhere in the app, reloads and the
 * sign-in redirect. It is written on every change and flushed when the page is hidden, and lives in
 * both localStorage and sessionStorage so either store failing does not lose it.
 */
export function readDraft<T>(key: string): T | null {
  for (const storage of [safeStorage("local"), safeStorage("session")]) {
    try {
      const raw = storage?.getItem(key);
      if (raw) return JSON.parse(raw) as T;
    } catch {
      // try the next store
    }
  }
  return null;
}

export function writeDraft<T>(key: string, value: T): void {
  const serialised = JSON.stringify(value);
  for (const storage of [safeStorage("local"), safeStorage("session")]) {
    try {
      storage?.setItem(key, serialised);
    } catch {
      // storage is a convenience only
    }
  }
}

export function clearDraft(key: string): void {
  for (const storage of [safeStorage("local"), safeStorage("session")]) {
    try {
      storage?.removeItem(key);
    } catch {
      // ignore
    }
  }
}

function safeStorage(kind: "local" | "session"): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

/** Persist `value` under `key` whenever it changes and when the page is hidden; `enabled` false skips it. */
export function useDraft<T>(key: string, value: T, enabled = true): void {
  const latest = useRef(value);
  latest.current = value;
  useEffect(() => {
    if (enabled) writeDraft(key, value);
  }, [key, value, enabled]);
  useEffect(() => {
    if (!enabled) return undefined;
    const flush = () => writeDraft(key, latest.current);
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", flush);
    };
  }, [key, enabled]);
}
