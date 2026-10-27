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
    <div className="auth-card">
      <h1>Вход</h1>
      {serverError && <div className="alert">{serverError}</div>}
      <form onSubmit={submit} noValidate>
        <div className="field">
          <label>Email или логин</label>
          <input type="text" autoComplete="username" value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => setTouched({ ...touched, email: true })}
            className={errors.email ? 'invalid' : ''} />
          {errors.email && <span className="error">{errors.email}</span>}
        </div>
        <div className="field">
          <label>Пароль</label>
          <input type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            onBlur={() => setTouched({ ...touched, password: true })}
            className={errors.password ? 'invalid' : ''} />
          {errors.password && <span className="error">{errors.password}</span>}
        </div>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? 'Вход…' : 'Войти'}
        </button>
      </form>
      <p className="muted">
        Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
      </p>
    </div>
  );
}
