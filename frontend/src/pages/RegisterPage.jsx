import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { apiError } from '../api/client';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function validate({ email, username, password, password2 }, touched) {
  const e = {};
  if (touched.email || email) {
    if (!email) e.email = 'Укажите email';
    else if (email.length > 254 || !EMAIL_RE.test(email)) e.email = 'Некорректный email';
  }
  if (touched.username || username) {
    if (!/^[a-zA-Z0-9_.-]{3,30}$/.test(username || ''))
      e.username = 'Логин: 3–30 символов, только буквы, цифры, _ . -';
  }
  if (touched.password || password) {
    if ((password || '').length < 8) e.password = 'Пароль минимум 8 символов';
  }
  if (touched.password2 || password2) {
    if (password2 !== password) e.password2 = 'Пароли не совпадают';
  }
  return e;
}

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', username: '', password: '', password2: '' });
  const [touched, setTouched] = useState({});
  const [serverError, setServerError] = useState('');
  const [busy, setBusy] = useState(false);

  const errors = validate(form, { ...touched, email: true, username: true, password: true, password2: true } && touched);
  const set = (k) => (ev) => setForm({ ...form, [k]: ev.target.value });
  const blur = (k) => () => setTouched({ ...touched, [k]: true });

  const submit = async (ev) => {
    ev.preventDefault();
    setTouched({ email: true, username: true, password: true, password2: true });
    const errs = validate(form, { email: true, username: true, password: true, password2: true });
    if (Object.keys(errs).length) return;
    setBusy(true);
    setServerError('');
    try {
      await register(form);
      navigate('/');
    } catch (err) {
      setServerError(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const field = (name, label, type, autoComplete) => (
    <div className="field">
      <label>{label}</label>
      <input
        type={type}
        name={name}
        autoComplete={autoComplete || 'off'}
        value={form[name]}
        onChange={set(name)}
        onBlur={blur(name)}
        className={touched[name] && errors[name] ? 'invalid' : ''}
      />
      {touched[name] && errors[name] && <span className="error">{errors[name]}</span>}
    </div>
  );

  return (
    <div className="auth-page page-enter">
      <div className="auth-bg" aria-hidden="true">
        <div className="auth-blob b1" /><div className="auth-blob b2" /><div className="auth-blob b3" />
      </div>
      <div className="auth-card glass-card">
        <h1 className="auth-title">Регистрация</h1>
        <p className="auth-sub">Создайте аккаунт и начните планировать задачи</p>
        {serverError && <div className="alert">{serverError}</div>}
        <form onSubmit={submit} noValidate>
          {field('email', 'Email', 'email', 'email')}
          {field('username', 'Логин', 'text', 'username')}
          {field('password', 'Пароль', 'password', 'new-password')}
          {field('password2', 'Повторите пароль', 'password', 'new-password')}
          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? (<><span className="spinner" /> Регистрация…</>) : 'Создать аккаунт'}
          </button>
        </form>
        <p className="auth-links">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </div>
    </div>
  );
}
