import axios from 'axios';

const api = axios.create({ baseURL: '/api', withCredentials: true });

// Access-токен хранится в httpOnly cookie `access` (устанавливает сервер).
// JS к нему не имеет доступа — заголовок Authorization больше не нужен.

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const status = err.response && err.response.status;
    const url = err.config && err.config.url;
    if (status === 401 && url !== '/auth/login/' && url !== '/auth/register/') {
      // токен в cookie истёк — пробуем один раз обновить и повторить запрос
      if (!err.config._retried) {
        try {
          await api.post('/auth/refresh/', {}, { _retried: true });
          return api({ ...err.config, _retried: true });
        } catch (e) { /* refresh не помог — уходим на логин */ }
      }
      localStorage.removeItem('user');
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export function apiError(err) {
  const data = err?.response?.data;
  if (!data) return 'Сервер недоступен. Попробуйте позже.';
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  if (data.errors) {
    return Object.values(data.errors).flat().join('; ');
  }
  return Object.values(data).flat().join('; ');
}

export default api;
