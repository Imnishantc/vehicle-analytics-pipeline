import React from 'react'

/** Hourly crossings bar chart rendered from /api/analytics/timeseries (real data only). */
export default function Timeline({ series }) {
  const items = series?.items || []
  const max = Math.max(1, ...items.map((i) => i.count))
  const W = 560, H = 160, pad = 24
  const bw = items.length ? Math.max(4, (W - pad * 2) / items.length - 4) : 0
  return (
    <div className="panel">
      <h2>Crossings per hour (UTC buckets, shown in local time)</h2>
      {!series && <div className="muted">Loading…</div>}
      {series && items.length === 0 && <div className="empty">No history for the selected range.</div>}
      {items.length > 0 && (
        <svg viewBox={`0 0 ${W} ${H + 20}`} role="img" aria-label="Crossings per hour">
          {items.map((i, n) => {
            const h = (i.count / max) * (H - pad)
            const x = pad + n * (bw + 4)
            return (
              <g key={i.t}>
                <rect x={x} y={H - h} width={bw} height={h} rx="2" className="barrect"><title>{`${new Date(i.t).toLocaleString()}: ${i.count}`}</title></rect>
                {items.length <= 12 && <text x={x + bw / 2} y={H + 14} textAnchor="middle" className="axis">{new Date(i.t).getHours()}h</text>}
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}
