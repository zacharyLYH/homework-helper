import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import { verifyCode, refreshToken, logout as apiLogout, type User } from "@/lib/api";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function checkSession() {
      try {
        const res = await fetch("/api/auth/me", { credentials: "include" });
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setUser(data);
          return;
        }
        await refreshToken();
        const meRes = await fetch("/api/auth/me", { credentials: "include" });
        if (meRes.ok) {
          const data = await meRes.json();
          if (!cancelled) setUser(data);
          return;
        }
      } catch {
        // Both failed — not authenticated
      }
      if (!cancelled) setUser(null);
    }

    checkSession().finally(() => {
      if (!cancelled) setLoading(false);
    });

    const interval = setInterval(async () => {
      try {
        await refreshToken();
      } catch {
        // refresh failed silently
      }
    }, 120_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const login = async (email: string, code: string) => {
    const result = await verifyCode(email, code);
    setUser(result.user);
  };

  const logout = async () => {
    await apiLogout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
