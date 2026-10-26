import axios from 'axios';

const api = axios.create({ baseURL: '/api', withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('access');
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
