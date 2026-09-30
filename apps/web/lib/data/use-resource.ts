"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";

export function useResource<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
) {
  const [state, setState] = useState<{
    key: string;
    baseKey: string;
    data: T | null;
    error: ApiError | Error | null;
  } | null>(null);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  const requestKey = key ? `${key}:${revision}` : null;
  useEffect(() => {
    if (!requestKey) return;
    const controller = new AbortController();
    let alive = true;
    load(controller.signal)
      .then((value) => {
        if (alive)
          setState({
            key: requestKey,
            baseKey: key!,
            data: value,
            error: null,
          });
      })
      .catch((reason) => {
        if (alive && reason?.name !== "AbortError")
          setState({
            key: requestKey,
            baseKey: key!,
            data: null,
            error:
              reason instanceof Error ? reason : new Error("Request failed"),
          });
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [requestKey, key, load]);
  return {
    data: state?.baseKey === key ? state.data : null,
    error: state?.key === requestKey ? state.error : null,
    loading: Boolean(requestKey && state?.key !== requestKey),
    refresh,
  };
}
