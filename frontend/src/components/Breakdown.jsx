import React from 'react'
import { colorHex, fmtNum } from '../format.js'

export default function Breakdown({ title, data, color = false }) {
  const items = data?.items || []
  const max = Math.max(1, ...items.map((i) => i.count))
  return (
    <div className="panel">
      <h2>{title}</h2>
      {!data && <div className="muted">Loading…</div>}
      {data && items.length === 0 && <div className="empty">No events match the current filters.</div>}
      <ul className="bars">
        {items.map((i) => (
          <li key={i.label}>
            <span className="lbl">
              {color && <i className="dot" style={{ background: colorHex(i.label) }} />}
              {i.label}
            </span>
            <span className="track"><span className="fill" style={{ width: `${(i.count / max) * 100}%`, background: color ? colorHex(i.label) : undefined }} /></span>
            <span className="num">{fmtNum(i.count)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
