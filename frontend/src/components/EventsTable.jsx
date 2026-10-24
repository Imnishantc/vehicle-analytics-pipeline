import React from 'react'
import { colorHex, fmtPct, fmtTime } from '../format.js'

export default function EventsTable({ data, loading, page, pageSize, onPage }) {
  const items = data?.items || []
  const total = data?.total || 0
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="panel">
      <div className="row between">
        <h2>Recent events</h2>
        <span className="muted small">{total.toLocaleString()} total</span>
      </div>
      <div className="scroll">
        <table>
          <thead>
            <tr><th>Time</th><th>Stream</th><th>Vehicle ID</th><th>Class</th><th>Color</th><th>Dir</th><th>Color conf.</th><th>Det. conf.</th></tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id}>
                <td>{fmtTime(e.event_time)}</td>
                <td>{e.stream_id}</td>
                <td>#{e.vehicle_id}</td>
                <td>{e.vehicle_class}</td>
                <td>{e.color ? <><i className="dot" style={{ background: colorHex(e.color) }} /> {e.color}</> : <span className="muted">unknown</span>}</td>
                <td><span className={`tag ${e.direction}`}>{e.direction}</span></td>
                <td>{fmtPct(e.color_confidence)}</td>
                <td>{fmtPct(e.class_confidence)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && data && items.length === 0 && <div className="empty">No events recorded yet. Start the pipeline to see crossings here.</div>}
        {loading && !data && <div className="muted pad">Loading…</div>}
      </div>
      <div className="row between pager">
        <button className="ghost" disabled={page === 0} onClick={() => onPage(page - 1)}>← Newer</button>
        <span className="muted small">Page {page + 1} of {pages}</span>
        <button className="ghost" disabled={page + 1 >= pages} onClick={() => onPage(page + 1)}>Older →</button>
      </div>
    </div>
  )
}
