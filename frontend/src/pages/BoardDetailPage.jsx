import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api, { apiError } from '../api/client';
import useToasts, { Toasts } from '../components/Toasts';

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const COLUMN_TINTS = [
  'rgba(99,102,241,.07)', 'rgba(217,70,239,.06)', 'rgba(16,185,129,.07)',
  'rgba(245,158,11,.07)', 'rgba(59,130,246,.07)', 'rgba(239,68,68,.05)',
];

// Fetch a protected file as blob (JWT передаётся в httpOnly cookie) and open/save it.
async function openFile(url, filename, save) {
  const r = await fetch(url, { credentials: 'include' });
  if (!r.ok) throw new Error('Не удалось открыть файл');
  const blob = await r.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objUrl;
  if (save) {
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(objUrl), 1000);
  } else {
    window.open(objUrl, '_blank', 'noopener');
    // revoke later so the new tab has time to load the blob
    setTimeout(() => URL.revokeObjectURL(objUrl), 60_000);
  }
}

function Attachment({ file, onDeleted }) {
  const isImage = IMAGE_TYPES.includes(file.mime) || /\.(jpe?g|png|webp)$/i.test(file.original_name);
  const del = async () => {
    if (!window.confirm(`Удалить файл «${file.original_name}»?`)) return;
    await api.delete(`/files/${file.id}/`);
    onDeleted(file.id);
  };
  const openInTab = async (e) => {
    e.preventDefault();
    try { await openFile(file.url, file.original_name, false); }
    catch (err) { alert(err.message); }
  };
  const saveFile = async (e) => {
    e.preventDefault();
    try { await openFile(file.url, file.original_name, true); }
    catch (err) { alert(err.message); }
  };
  return (
    <div className="attachment">
      {isImage ? (
        <a className="attach-chip" href={file.url} onClick={openInTab}>
          <img src={file.url} alt={file.original_name} className="thumb" />
        </a>
      ) : (
        <a className="attach-chip" href={file.url} download={file.original_name} onClick={saveFile}>
          📄 {file.original_name}
        </a>
      )}
      <button className="btn-icon danger" title="Удалить файл" onClick={del}>✕</button>
    </div>
  );
}

function CardItem({ card, onChanged, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(card.title);
  const [description, setDescription] = useState(card.description || '');
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
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
    <div className={`kanban-card card-item${dragging ? ' dragging' : ''}`} draggable={!editing}
      onDragStart={(e) => { setDragging(true); e.dataTransfer.setData('text/plain', String(card.id)); }}
      onDragEnd={() => setDragging(false)}>
      {editing ? (
        <>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название" />
          <textarea className="textarea" rows="3" value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="Описание" />
          {error && <span className="error-text">{error}</span>}
          <div className="tile-actions">
            <button className="btn btn-primary btn-sm" onClick={save}>Сохранить</button>
            <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(false); setTitle(card.title); setDescription(card.description || ''); setError(''); }}>Отмена</button>
          </div>
        </>
      ) : (
        <>
          <div className="card-title">{card.title}</div>
          {card.description && <div className="card-desc">{card.description}</div>}
          {(card.files || []).length > 0 && (
            <div className="attachments">
              {card.files.map((f) => <Attachment key={f.id} file={f} onDeleted={removeFile} />)}
            </div>
          )}
          {error && <span className="error-text">{error}</span>}
          <div className="card-footer">
            <span className="small muted">{uploading ? '⏳ Загрузка…' : ''}</span>
            <span className="card-actions">
              <button className="btn-icon" title="Редактировать" onClick={() => setEditing(true)}>✏️</button>
              <label className="btn-icon" title="Прикрепить файл" style={{ cursor: 'pointer' }}>
                📎
                <input ref={fileRef} type="file" hidden onChange={upload} disabled={uploading} />
              </label>
              <button className="btn-icon danger" title="Удалить карточку" onClick={() => onDelete(card)}>🗑</button>
            </span>
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
  const [dragOverCol, setDragOverCol] = useState(null);
  const { toasts, push, remove } = useToasts();

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
      push(`Колонка «${t}» создана`);
      load();
    } catch (e) { setServerError(apiError(e)); }
  };

  const deleteColumn = async (col) => {
    if (!window.confirm(`Удалить колонку «${col.title}»?`)) return;
    try {
      await api.delete(`/columns/${col.id}/`);
      push('Колонка удалена');
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
      push('Карточка удалена');
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
    setDragOverCol(null);
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

  if (!board) {
    return (
      <div className="center">
        <span className="spinner dark" style={{ width: 28, height: 28 }} />
        <p className="muted">Загрузка доски…</p>
      </div>
    );
  }

  return (
    <div className="page-enter">
      <div className="board-header">
        <div>
          <h1>{board.title}</h1>
          {board.description && <p className="muted">{board.description}</p>}
        </div>
        <Link to="/" className="back-link">← К доскам</Link>
      </div>
      {serverError && <div className="alert">{serverError}</div>}

      <div className="board-columns">
        {columns.map((col, idx) => (
          <div className="column glass-card" key={col.id}
            style={{ background: COLUMN_TINTS[idx % COLUMN_TINTS.length] }}
            onDragOver={(e) => { e.preventDefault(); setDragOverCol(col.id); }}
            onDragLeave={() => setDragOverCol((v) => (v === col.id ? null : v))}
            onDrop={(e) => dropOnColumn(col, e)}>
            <div className="column-header column-title">
              <strong>{col.title}</strong>
              <span className="column-count">{col.cards.length}</span>
              <span className="col-actions">
                <button className="btn-icon" title="Добавить карточку" onClick={() => addCard(col)}>＋</button>
                <button className="btn-icon danger" title="Удалить колонку" onClick={() => deleteColumn(col)}>✕</button>
              </span>
            </div>
            <div className="column-body stagger">
              {col.cards.map((card) => (
                <CardItem key={card.id} card={card} onChanged={updateCard} onDelete={deleteCard} />
              ))}
              {col.cards.length === 0 && (
                <div className="drop-zone">Перетащите сюда карточку</div>
              )}
            </div>
          </div>
        ))}
        <form className="column add-column glass-card" onSubmit={addColumn}>
          <input className="input" placeholder="Новая колонка" value={newColTitle}
            onChange={(e) => setNewColTitle(e.target.value)} />
          <button className="btn btn-primary btn-sm">Добавить</button>
        </form>
      </div>

      <Toasts toasts={toasts} onRemove={remove} />
    </div>
  );
}
