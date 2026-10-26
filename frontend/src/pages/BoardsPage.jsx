import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { apiError } from '../api/client';

export default function BoardsPage() {
  const [boards, setBoards] = useState([]);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState({ title: '', description: '' });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback((q = '') => {
    setLoading(true);
    api.get('/boards/', { params: q ? { search: q } : {} })
      .then((r) => setBoards(r.data.results ?? r.data))
      .catch((e) => setServerError(apiError(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(search); }, [search, load]);

  const createBoard = async (ev) => {
    ev.preventDefault();
    const errs = {};
    const title = form.title.trim();
    if (!title || title.length > 120) errs.title = 'Название: от 1 до 120 символов';
    if (form.description.length > 2000) errs.description = 'Описание: максимум 2000 символов';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      await api.post('/boards/', form);
      setForm({ title: '', description: '' });
      load(search);
    } catch (e) {
      setServerError(apiError(e));
    }
  };

  const exportExcel = async () => {
    setServerError('');
    try {
      const r = await api.get('/boards/export/', { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `kanban_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setServerError(apiError(e));
    }
  };

  const removeBoard = async (b) => {
    if (!window.confirm(`Удалить доску «${b.title}» со всеми колонками и карточками?`)) return;
    try {
      await api.delete(`/boards/${b.id}/`);
      load(search);
    } catch (e) {
      setServerError(apiError(e));
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Мои доски</h1>
        <button className="btn btn-outline" onClick={exportExcel}
          title="Выгрузить список досок в .xlsx">Экспорт в Excel</button>
      </div>
      {serverError && <div className="alert">{serverError}</div>}

      <form className="board-form card-panel" onSubmit={createBoard}>
        <div className="field">
          <input placeholder="Название новой доски" value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className={errors.title ? 'invalid' : ''} />
          {errors.title && <span className="error">{errors.title}</span>}
        </div>
        <div className="field">
          <textarea placeholder="Описание (необязательно)" rows="2" value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className={errors.description ? 'invalid' : ''} />
          {errors.description && <span className="error">{errors.description}</span>}
        </div>
        <button className="btn btn-primary">Создать доску</button>
      </form>

      <input className="search" placeholder="Поиск по названию…"
        value={search} onChange={(e) => setSearch(e.target.value)} />

      {loading ? <div className="center">Загрузка…</div> : (
        <div className="grid">
          {boards.length === 0 && <p className="muted">Досок пока нет — создайте первую.</p>}
          {boards.map((b) => (
            <div className="board-tile card-panel" key={b.id}>
              <Link to={`/boards/${b.id}`} className="board-title">{b.title}</Link>
              {b.description && <p className="muted desc">{b.description}</p>}
              <div className="tile-actions">
                <Link to={`/boards/${b.id}`} className="btn btn-outline">Открыть</Link>
                <button className="btn btn-danger" onClick={() => removeBoard(b)}>Удалить</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
