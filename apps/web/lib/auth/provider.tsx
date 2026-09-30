"use client";

import {
  createClient,
  type Session,
  type SupabaseClient,
} from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ApiClient } from "@/lib/api/client";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
export const authConfigured = Boolean(
  url && key && !url.includes("your-project") && !key.includes("your-public"),
);
let browserClient: SupabaseClient | null = null;
export function supabase(): SupabaseClient | null {
  if (!authConfigured || !url || !key) return null;
  if (!browserClient)
    browserClient = createClient(url, key, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    });
  return browserClient;
}

interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  api: ApiClient;
  signOut: () => Promise<void>;
}
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(authConfigured);
  useEffect(() => {
    const client = supabase();
    if (!client) return;
    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });
    void client.auth.getSession().then(({ data, error }) => {
      if (!error) setSession(data.session);
      setLoading(false);
    });
    return () => subscription.unsubscribe();
  }, []);
  const signOut = useCallback(async () => {
    await supabase()?.auth.signOut();
    setSession(null);
    router.replace("/auth/sign-in");
  }, [router]);
  const api = useMemo(
    () =>
      new ApiClient(
        async () => {
          const { data } = (await supabase()?.auth.getSession()) ?? {
            data: { session: null },
          };
          return data.session?.access_token ?? null;
        },
        () => {
          setSession(null);
          void supabase()?.auth.signOut();
          router.replace("/auth/sign-in?expired=1");
        },
      ),
    [router],
  );
  return (
    <AuthContext.Provider value={{ session, loading, api, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is required");
  return value;
}
