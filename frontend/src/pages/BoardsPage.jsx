import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { apiError } from '../api/client';

const PAGE_SIZES = [3, 5, 9];

export default function BoardsPage() {
  const [boards, setBoards] = useState([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [limit, setLimit] = useState(() => Number(localStorage.getItem('boards_limit')) || 5);
  const [category, setCategory] = useState('');
  const [categories, setCategories] = useState([]);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState({ title: '', description: '', category: '' });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const params = { page, limit };
    if (search) params.search = search;
    if (category) params.category = category;
    api.get('/boards/', { params })
      .then((r) => {
        setBoards(r.data.results ?? r.data);
        setPages(r.data.pages ?? 1);
      })
      .catch((e) => setServerError(apiError(e)))
      .finally(() => setLoading(false));
  }, [page, limit, search, category]);

  const loadCategories = useCallback(() => {
    api.get('/boards/categories/')
      .then((r) => setCategories(r.data))
      .catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadCategories(); }, [loadCategories]);

  // меняли поиск/фильтр — сбрасываем на первую страницу
  useEffect(() => { setPage(1); }, [search, category, limit]);

  const changeLimit = (n) => {
    setLimit(n);
    localStorage.setItem('boards_limit', String(n));
  };

  const createBoard = async (ev) => {
    ev.preventDefault();
    const errs = {};
    const title = form.title.trim();
    if (!title || title.length > 120) errs.title = 'Название: от 1 до 120 символов';
    if (form.description.length > 2000) errs.description = 'Описание: максимум 2000 символов';
    if (form.category.length > 50) errs.category = 'Метка: максимум 50 символов';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      await api.post('/boards/', form);
      setForm({ title: '', description: '', category: '' });
      load();
      loadCategories();
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
      load();
      loadCategories();
    } catch (e) {
      setServerError(apiError(e));
    }
  };

  // страницы: показываем до 7 кнопок с «…», если их много
  const pageButtons = [];
  for (let p = 1; p <= pages; p++) {
    if (pages <= 7 || p === 1 || p === pages || Math.abs(p - page) <= 2) {
      pageButtons.push(p);
    } else if (pageButtons[pageButtons.length - 1] !== '…') {
      pageButtons.push('…');
    }
  }

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
        <div className="field">
          <input placeholder="Метка: Работа, Учеба… (необязательно)" value={form.category}
            maxLength={50}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            className={errors.category ? 'invalid' : ''} />
          {errors.category && <span className="error">{errors.category}</span>}
        </div>
        <button className="btn btn-primary">Создать доску</button>
      </form>

      <div className="toolbar">
        <input className="search" placeholder="Поиск по названию…"
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="filter" value={category}
          onChange={(e) => setCategory(e.target.value)}
          title="Фильтр по метке">
          <option value="">Все метки</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          {categories.length > 0 && <option value="none">Без метки</option>}
        </select>
        <div className="page-size" title="Досок на странице">
          {PAGE_SIZES.map((n) => (
            <button key={n}
              className={`btn btn-sm ${limit === n ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => changeLimit(n)}>{n}</button>
          ))}
        </div>
      </div>

      {loading ? <div className="center">Загрузка…</div> : (
        <div className="grid">
          {boards.length === 0 && <p className="muted">
            {search || category ? 'Ничего не найдено — измените поиск или фильтр.' : 'Досок пока нет — создайте первую.'}
          </p>}
          {boards.map((b) => (
            <div className="board-tile card-panel" key={b.id}>
              <Link to={`/boards/${b.id}`} className="board-title">{b.title}</Link>
              {b.category && <span className="badge"
                onClick={() => setCategory(b.category)}
                title="Фильтровать по этой метке">{b.category}</span>}
              {b.description && <p className="muted desc">{b.description}</p>}
              <div className="tile-actions">
                <Link to={`/boards/${b.id}`} className="btn btn-outline">Открыть</Link>
                <button className="btn btn-danger" onClick={() => removeBoard(b)}>Удалить</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {pages > 1 && (
        <div className="pagination">
          <button className="btn btn-outline btn-sm" disabled={page <= 1}
            onClick={() => setPage(page - 1)}>← Назад</button>
          {pageButtons.map((p, i) => p === '…'
            ? <span className="muted" key={`d${i}`}>…</span>
            : <button key={p}
                className={`btn btn-sm ${p === page ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setPage(p)}>{p}</button>)}
          <button className="btn btn-outline btn-sm" disabled={page >= pages}
            onClick={() => setPage(page + 1)}>Вперёд →</button>
        </div>
      )}
    </div>
  );
}
