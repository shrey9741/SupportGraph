import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setToken } from "./api.js";

const AuthContext = createContext(null);
const LOCAL_USER = { id: 0, name: "Local user", email: "local@localhost", role: "admin" };

/** status: loading | anonymous | ready | error. When the server runs with login off, the user is "Local user". */
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", user: null, authRequired: true, error: null });

  const refresh = useCallback(async () => {
    setState((s) => ({ ...s, status: "loading", error: null }));
    try {
      const health = await api.health();
      if (!health.auth_required) {
        setState({ status: "ready", user: LOCAL_USER, authRequired: false, error: null });
        return;
      }
      if (!api.hasToken()) {
        setState({ status: "anonymous", user: null, authRequired: true, error: null });
        return;
      }
      try {
        const user = await api.me();
        setState({ status: "ready", user, authRequired: true, error: null });
      } catch {
        setToken(null);
        setState({ status: "anonymous", user: null, authRequired: true, error: null });
      }
    } catch (e) {
      setState({ status: "error", user: null, authRequired: true, error: e.message });
    }
  }, []);

  useEffect(() => {
    api.setUnauthorizedHandler(() => setState((s) => ({ ...s, status: "anonymous", user: null })));
    refresh();
  }, [refresh]);

  const login = useCallback(async (email, password) => {
    const res = await api.login(email, password);
    setToken(res.access_token);
    setState({ status: "ready", user: res.user, authRequired: true, error: null });
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setState((s) => ({ ...s, status: "anonymous", user: null }));
  }, []);

  const value = useMemo(() => ({ ...state, login, logout, refresh }), [state, login, logout, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
