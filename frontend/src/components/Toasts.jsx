import { useEffect, useState } from 'react';

/** Простые всплывающие уведомления (тосты) с автоскрытием. */
export default function useToasts() {
  const [toasts, setToasts] = useState([]);

  const push = (text, type = 'success') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, type }]);
  };
  const remove = (id) => setToasts((t) => t.filter((x) => x.id !== id));

  return { toasts, push, remove };
}

export function Toasts({ toasts, onRemove }) {
  if (!toasts.length) return null;
  return (
    <div className="toast-wrap">
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} onRemove={onRemove} />
      ))}
    </div>
  );
}

function Toast({ toast, onRemove }) {
  const [hide, setHide] = useState(false);
  useEffect(() => {
    const h = setTimeout(() => setHide(true), 2600);
    const d = setTimeout(() => onRemove(toast.id), 3000);
    return () => { clearTimeout(h); clearTimeout(d); };
  }, [toast.id, onRemove]);
  return (
    <div className={`toast ${toast.type}${hide ? ' hide' : ''}`}>{toast.text}</div>
  );
}
