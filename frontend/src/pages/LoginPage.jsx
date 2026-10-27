import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { apiError } from '../api/client';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState({});
  const [serverError, setServerError] = useState('');
  const [busy, setBusy] = useState(false);

  const errors = {};
  if (touched.email && !email) errors.email = 'Введите email';
  if (touched.password && !password) errors.password = 'Введите пароль';

  const submit = async (ev) => {
    ev.preventDefault();
    setTouched({ email: true, password: true });
    if (!email || !password) return;
    setBusy(true);
    setServerError('');
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setServerError(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page page-enter">
      <div className="auth-bg" aria-hidden="true">
        <div className="auth-blob b1" /><div className="auth-blob b2" /><div className="auth-blob b3" />
      </div>
      <div className="auth-card glass-card">
        <h1 className="auth-title">Вход</h1>
        <p className="auth-sub">Рады видеть вас снова на вашей доске</p>
        {serverError && <div className="alert">{serverError}</div>}
        <form onSubmit={submit} noValidate>
          <div className="field">
            <label>Email или логин</label>
            <input className={`input${errors.email ? ' invalid' : ''}`} type="text" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setTouched({ ...touched, email: true })} />
            {errors.email && <span className="error-text">{errors.email}</span>}
          </div>
          <div className="field">
            <label>Пароль</label>
            <input className={`input${errors.password ? ' invalid' : ''}`} type="password" value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => setTouched({ ...touched, password: true })} />
            {errors.password && <span className="error-text">{errors.password}</span>}
          </div>
          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? (<><span className="spinner" /> Вход…</>) : 'Войти'}
          </button>
        </form>
        <p className="auth-links">
          Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
        </p>
      </div>
    </div>
  );
}
