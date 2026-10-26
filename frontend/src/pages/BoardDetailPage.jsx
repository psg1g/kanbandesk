import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api, { apiError } from '../api/client';

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

function Attachment({ file, onDeleted }) {
  const isImage = IMAGE_TYPES.includes(file.mime) || /\.(jpe?g|png|webp)$/i.test(file.original_name);
  const del = async () => {
    if (!window.confirm(`Удалить файл «${file.original_name}»?`)) return;
    await api.delete(`/files/${file.id}/`);
    onDeleted(file.id);
  };
  return (
    <div className="attachment">
      {isImage ? (
        <a href={file.url} target="_blank" rel="noreferrer">
          <img src={file.url} alt={file.original_name} className="thumb" />
        </a>
      ) : (
        <a href={file.url} download={file.original_name}>📄 {file.original_name}</a>
      )}
      <button className="btn btn-danger btn-sm" onClick={del}>×</button>
    </div>
  );
}

function CardItem({ card, onChanged, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(card.title);
  const [description, setDescription] = useState(card.description || '');
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const save = async () => {
    const t = title.trim();
    if (!t || t.length > 120) { setError('Название карточки: 1–120 символов'); return; }
    if (description.length > 2000) { setError('Описание: максимум 2000 символов'); return; }
    try {
      const r = await api.patch(`/cards/${card.id}/`, { title: t, description });
      onChanged(r.data);
      setEditing(false);
      setError('');
    } catch (e) { setError(apiError(e)); }
  };

  const upload = async (ev) => {
    const f = ev.target.files?.[0];
    if (!f) return;
    setUploading(true);
    setError('');
    const fd = new FormData();
    fd.append('file', f);
    try {
      const r = await api.post(`/cards/${card.id}/files/`, fd);
      onChanged({ ...card, files: [...(card.files || []), r.data] });
      if (!IMAGE_TYPES.includes(r.data.mime)) window.location.reload(); // приватный url требует JWT-заголовка
    } catch (e) {
      setError(apiError(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const removeFile = (id) =>
    onChanged({ ...card, files: (card.files || []).filter((f) => f.id !== id) });

  return (
    <div className="kanban-card card-panel" draggable={!editing}
      onDragStart={(e) => e.dataTransfer.setData('text/plain', String(card.id))}>
      {editing ? (
        <>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название" />
          <textarea rows="3" value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="Описание" />
          {error && <span className="error">{error}</span>}
          <div className="tile-actions">
            <button className="btn btn-primary btn-sm" onClick={save}>Сохранить</button>
            <button className="btn btn-outline btn-sm" onClick={() => { setEditing(false); setTitle(card.title); setDescription(card.description || ''); setError(''); }}>Отмена</button>
          </div>
        </>
      ) : (
        <>
          <div className="card-title">{card.title}</div>
          {card.description && <div className="card-desc">{card.description}</div>}
          {(card.files || []).map((f) => <Attachment key={f.id} file={f} onDeleted={removeFile} />)}
          {error && <span className="error">{error}</span>}
          <div className="tile-actions">
            <button className="btn btn-outline btn-sm" onClick={() => setEditing(true)}>✏️</button>
            <label className="btn btn-outline btn-sm">
              {uploading ? 'Загрузка…' : '📎 Файл'}
              <input ref={fileRef} type="file" hidden onChange={upload} disabled={uploading} />
            </label>
            <button className="btn btn-danger btn-sm" onClick={() => onDelete(card)}>🗑</button>
          </div>
        </>
      )}
    </div>
  );
}

export default function BoardDetailPage() {
  const { id } = useParams();
  const [board, setBoard] = useState(null);
  const [columns, setColumns] = useState([]);
  const [serverError, setServerError] = useState('');
  const [newColTitle, setNewColTitle] = useState('');
  const dragOverCol = useRef(null);

  const load = useCallback(() => {
    api.get(`/boards/${id}/`)
      .then((r) => {
        setBoard(r.data);
        setColumns(
          (r.data.columns || [])
            .slice()
            .sort((a, b) => a.position - b.position)
            .map((c) => ({ ...c, cards: (c.cards || []).slice().sort((a, b) => a.position - b.position) }))
        );
      })
      .catch((e) => setServerError(apiError(e)));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const addColumn = async (ev) => {
    ev.preventDefault();
    const t = newColTitle.trim();
    if (!t || t.length > 120) { setServerError('Название колонки: 1–120 символов'); return; }
    try {
      await api.post('/columns/', { board_id: Number(id), title: t });
      setNewColTitle('');
      setServerError('');
      load();
    } catch (e) { setServerError(apiError(e)); }
  };

  const deleteColumn = async (col) => {
    if (!window.confirm(`Удалить колонку «${col.title}»?`)) return;
    try {
      await api.delete(`/columns/${col.id}/`);
      load();
    } catch (e) {
      setServerError(apiError(e)); // например, «нельзя удалить непустую колонку»
    }
  };

  const addCard = async (col) => {
    const title = window.prompt('Название новой карточки:');
    if (!title || !title.trim()) return;
    try {
      await api.post('/cards/', { column_id: col.id, title: title.trim(), description: '' });
      load();
    } catch (e) { setServerError(apiError(e)); }
  };

  const deleteCard = async (card) => {
    if (!window.confirm(`Удалить карточку «${card.title}»?`)) return;
    try {
      await api.delete(`/cards/${card.id}/`);
      load();
    } catch (e) { setServerError(apiError(e)); }
  };

  const updateCard = (updated) => {
    setColumns((cols) => cols.map((c) => ({
      ...c,
      cards: c.cards.map((k) => (k.id === updated.id ? { ...k, ...updated } : k)),
    })));
  };

  const dropOnColumn = async (col, e) => {
    e.preventDefault();
    const cardId = Number(e.dataTransfer.getData('text/plain'));
    if (!cardId) return;
    const source = columns.find((c) => c.cards.some((k) => k.id === cardId));
    if (!source) return;
    const pos = col.cards.length;
    try {
      await api.patch(`/cards/${cardId}/move/`, { column_id: col.id, position: pos });
      setServerError('');
      load();
    } catch (err) { setServerError(apiError(err)); }
  };

  if (!board) return <div className="center">Загрузка…</div>;

  return (
    <div>
      <div className="board-header">
        <h1>{board.title}</h1>
        <Link to="/" className="btn btn-outline">← К доскам</Link>
      </div>
      {board.description && <p className="muted">{board.description}</p>}
      {serverError && <div className="alert">{serverError}</div>}

      <div className="board-columns">
        {columns.map((col) => (
          <div className="column card-panel" key={col.id}
            onDragOver={(e) => { e.preventDefault(); dragOverCol.current = col.id; }}
            onDrop={(e) => dropOnColumn(col, e)}>
            <div className="column-header">
              <strong>{col.title}</strong>
              <span className="col-actions">
                <button className="btn btn-outline btn-sm" title="Добавить карточку" onClick={() => addCard(col)}>＋</button>
                <button className="btn btn-danger btn-sm" title="Удалить колонку" onClick={() => deleteColumn(col)}>×</button>
              </span>
            </div>
            {col.cards.map((card) => (
              <CardItem key={card.id} card={card} onChanged={updateCard} onDelete={deleteCard} />
            ))}
            {col.cards.length === 0 && <p className="muted small">Перетащите сюда карточку</p>}
          </div>
        ))}
        <form className="column add-column" onSubmit={addColumn}>
          <input placeholder="Новая колонка" value={newColTitle}
            onChange={(e) => setNewColTitle(e.target.value)} />
          <button className="btn btn-primary btn-sm">Добавить</button>
        </form>
      </div>
    </div>
  );
}
