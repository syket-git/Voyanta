"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { listThreads, type ThreadSummary } from "@/lib/voyanta";

interface ThreadsContextValue {
  threads: ThreadSummary[];
  loading: boolean;
  refresh: () => Promise<void>;
  applyLocal: (threads: ThreadSummary[]) => void;
}

const ThreadsContext = createContext<ThreadsContextValue | null>(null);

export function useThreads() {
  const context = useContext(ThreadsContext);

  if (!context) {
    throw new Error("useThreads must be used inside ThreadsProvider.");
  }

  return context;
}

export function ThreadsProvider({ children }: { children: React.ReactNode }) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setThreads(await listThreads());
    } catch {
      // A failed refresh leaves the last known list in place; the sidebar is not worth
      // interrupting the conversation over.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    listThreads()
      .then((next) => {
        if (!cancelled) setThreads(next);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ThreadsContext.Provider
      value={{ threads, loading, refresh, applyLocal: setThreads }}
    >
      {children}
    </ThreadsContext.Provider>
  );
}
