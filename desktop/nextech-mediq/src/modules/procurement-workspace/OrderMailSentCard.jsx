import { useEffect } from 'react';

// Centre-screen confirmation after an order was mailed to the supplier
// (Procurement "Export & Mail"). Closes on its own after AUTO_CLOSE_MS, on
// Esc, on the backdrop or on Done.
const AUTO_CLOSE_MS = 9000;

const fmtMoney = (v) => (v ? `₹${Math.round(v).toLocaleString('en-IN')}` : '—');

export default function OrderMailSentCard({ sent, onClose }) {
  useEffect(() => {
    if (!sent) return undefined;
    const timer = setTimeout(onClose, AUTO_CLOSE_MS);
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { clearTimeout(timer); window.removeEventListener('keydown', onKey); };
  }, [sent, onClose]);
  if (!sent) return null;

  const stats = [
    ['Store', sent.store],
    ['Files', sent.files],
    ['Products', sent.products],
    ['Approx. bill', fmtMoney(sent.billValue)],
  ];
  return (
    <div className="oms-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="oms-card" role="alertdialog" aria-modal="true" aria-labelledby="oms-title">
        <div className="oms-glow" aria-hidden="true" />
        <div className="oms-badge" aria-hidden="true">
          <svg viewBox="0 0 52 52"><circle className="oms-ring" cx="26" cy="26" r="23" /><path className="oms-tick" d="M15 27.5l7.5 7.5L38 19" /></svg>
        </div>
        <div className="oms-eyebrow">Order sent</div>
        <h2 id="oms-title" className="oms-title">{sent.supplier}</h2>
        <div className="oms-sub">
          <span className="oms-code">{sent.supplierCode}</span>
          {sent.to && <span className="oms-to" title={sent.to}>✉ {sent.to}</span>}
        </div>
        <div className="oms-stats">
          {stats.map(([label, value]) => (
            <div key={label} className="oms-stat">
              <span className="oms-stat-value">{value}</span>
              <span className="oms-stat-label">{label}</span>
            </div>
          ))}
        </div>
        <div className="oms-foot">
          <span>{sent.orderNo ? `Order ${sent.orderNo} · ` : ''}{sent.at}</span>
          <button type="button" className="oms-done" onClick={onClose} autoFocus>Done</button>
        </div>
        <div className="oms-timer" style={{ animationDuration: `${AUTO_CLOSE_MS}ms` }} aria-hidden="true" />
      </div>
    </div>
  );
}
