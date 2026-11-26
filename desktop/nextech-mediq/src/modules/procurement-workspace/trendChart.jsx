import { createPortal } from 'react-dom';

// Shared In / Out / Stock bar rendering for the stock-movement charts --
// Monthly Trend (OwTrendChart) and Procurement's All Stores panel -- so both
// draw a month the same way: three adjacent .ow-chart-bar bars centred in the
// month (styles.css .ow-chart-bars: flex-end, centre, 4px gap, 5-15px bars),
// height as a share of the chart's max, value label on top of each bar, and a
// zero as a thin pale 3px marker at the baseline labelled 0.

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// 'YYYY-MM' -> 'Sep 2026'.
export function fmtMonthLabel(ym) {
  const [y, m] = String(ym || '').split('-');
  const i = Number(m) - 1;
  return i >= 0 && i < 12 ? `${MONTH_NAMES[i]} ${y}` : (ym || '—');
}

// The largest In / Out / Stock value over `rows` (at least 1) -- the top of
// the chart's scale.
export function trendMax(rows, series) {
  return Math.max(1, ...rows.flatMap((r) => series.map((s) => Number(r[s.key]) || 0)));
}

// One month's bars. series: [{ key, cls }] (cls = in / out / stock);
// fmt formats the label shown on top of each bar.
export function TrendBars({ series, row, max, fmt }) {
  return (
    <div className="ow-chart-bars">
      {series.map((s) => {
        const v = Number(row[s.key]) || 0;
        const isZero = v === 0;
        const pct = isZero ? 0 : Math.max(4, (v / max) * 100);
        return (
          <div
            key={s.key}
            className={`ow-chart-bar ow-chart-bar--${s.cls}${isZero ? ' is-zero' : ''}`}
            style={{ height: isZero ? '3px' : `${pct}%` }}
          >
            <span className="ow-chart-val">{fmt(v)}</span>
          </div>
        );
      })}
    </div>
  );
}

// Floating month tooltip above anchorRect -- portaled to document.body so it
// is never clipped by the side panel's overflow:hidden ancestors.
export function TrendTip({ anchorRect, width = 224, children }) {
  if (!anchorRect) return null;
  const left = Math.min(Math.max(anchorRect.left + anchorRect.width / 2, width / 2 + 8), window.innerWidth - width / 2 - 8);
  const top = anchorRect.top - 8;
  return createPortal(
    <div className="ow-chart-tip" role="tooltip" style={{ position: 'fixed', top, left, width }}>
      {children}
    </div>,
    document.body
  );
}
