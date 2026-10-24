import React from 'react'
import { fmtTime } from '../format.js'

const LABEL = {
  running: ['ok', 'Running'], stale: ['warn', 'Stale (no heartbeat)'], no_pipeline: ['warn', 'Pipeline never started'],
  error: ['bad', 'Error'], eos: ['warn', 'Stream ended'], stopped: ['warn', 'Stopped'], starting: ['warn', 'Starting'],
}

export default function StatusPanel({ status }) {
  const items = status?.items || []
  return (
    <div className="panel">
      <h2>Pipeline status</h2>
      {!status && <div className="muted">Loading…</div>}
      {status && items.length === 0 && <div className="empty">No streams registered. They appear once the pipeline starts.</div>}
      {items.map((s) => {
        const [cls, txt] = LABEL[s.state] || ['warn', s.state]
        return (
          <div className="stream" key={s.stream_id}>
            <div className="row between"><strong>{s.stream_id}</strong><span className={`pill ${cls}`}>{txt}</span></div>
            <div className="muted small">{s.rtsp_url}</div>
            <div className="muted small">
              {s.fps != null ? `${s.fps.toFixed(1)} FPS · ` : ''}{s.frames != null ? `${s.frames.toLocaleString()} frames · ` : ''}
              last event {fmtTime(s.last_event)}
            </div>
            {s.detail && <div className={`small ${s.state === 'error' ? 'bad-text' : 'muted'}`}>{s.detail}</div>}
          </div>
        )
      })}
    </div>
  )
}
