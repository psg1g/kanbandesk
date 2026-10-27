import { createContext, useContext, useEffect, useState } from 'react';
import api from './api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Access-токен хранится в httpOnly cookie — JS его не видит.
  // Проверяем сессию запросом /auth/me/ (401 = не залогинен).
  useEffect(() => {
    api.get('/auth/me/')
      .then((r) => setUser(r.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const r = await api.post('/auth/login/', { email, password });
    setUser(r.data.user);
    return r.data.user;
  };

  const register = async (payload) => {
    const r = await api.post('/auth/register/', payload);
    setUser(r.data.user);
    return r.data.user;
  };

  const logout = async () => {
    try { await api.post('/auth/logout/'); } catch (e) { /* noop */ }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
