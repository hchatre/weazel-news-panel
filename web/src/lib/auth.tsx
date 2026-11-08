"use client";
import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken, Me } from "./api";

type AuthState = { me: Me | null; loading: boolean; can: (p: string) => boolean; login: (e: string, p: string) => Promise<void>; loginWithToken: (t: string) => Promise<void>; logout: () => void };
const Ctx = createContext<AuthState>(null as unknown as AuthState);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    // auth_mode "local" needs no token; the API decides, so always ask once.
    api<Me>("/auth/me").then(setMe).catch(() => { setToken(null); setMe(null); }).finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string }>("/auth/login", { method: "POST", body: { email, password } });
    setToken(r.access_token);
    setMe(await api<Me>("/auth/me"));
  }, []);
  const loginWithToken = useCallback(async (token: string) => { setToken(token); setMe(await api<Me>("/auth/me")); }, []);
  const logout = useCallback(() => { setToken(null); setMe(null); router.push("/login"); }, [router]);
  const can = useCallback((p: string) => !!me?.permissions.includes(p), [me]);
  return <Ctx.Provider value={{ me, loading, can, login, loginWithToken, logout }}>{children}</Ctx.Provider>;
}
export const useAuth = () => useContext(Ctx);
export { getToken };
