import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import RegisterPage from './pages/RegisterPage';
import LoginPage from './pages/LoginPage';
import BoardsPage from './pages/BoardsPage';
import BoardDetailPage from './pages/BoardDetailPage';

function Private({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Загрузка…</div>;
  if (user) return <Navigate to="/" replace />;
  return children;
}

export function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  return (
    <header className="header">
      <span className="logo" onClick={() => navigate('/')}>📎 Канбан-доска</span>
      <div className="header-right">
        <span className="username">{user.username}</span>
        <button className="btn btn-outline" onClick={async () => { await logout(); navigate('/login'); }}>
          Выйти
        </button>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <>
      <Header />
      <main className="container">
        <Routes>
          <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
          <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
          <Route path="/" element={<Private><BoardsPage /></Private>} />
          <Route path="/boards/:id" element={<Private><BoardDetailPage /></Private>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
