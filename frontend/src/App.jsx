import React, { useCallback, useEffect, useRef, useState } from 'react'
import { get, liveUrl } from './api.js'
import { fmtNum, fmtTime, localToIso } from './format.js'
import Breakdown from './components/Breakdown.jsx'
import EventsTable from './components/EventsTable.jsx'
import Timeline from './components/Timeline.jsx'
import StatusPanel from './components/StatusPanel.jsx'
import LivePlayer from './components/LivePlayer.jsx'

const PAGE = 15
const EMPTY = { stream_id: '', color: '', vehicle_class: '', direction: '', start: '', end: '' }

export default function App() {
  const [filters, setFilters] = useState(EMPTY)
  const [page, setPage] = useState(0)
  const [data, setData] = useState({ summary: null, colors: null, classes: null, events: null, series: null, status: null })
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [live, setLive] = useState('connecting')
  const [lastUpdate, setLastUpdate] = useState(null)
  const filtersRef = useRef(filters)
  const pageRef = useRef(page)
  filtersRef.current = filters
  pageRef.current = page

  const load = useCallback(async () => {
    const f = filtersRef.current
    const range = { start: localToIso(f.start), end: localToIso(f.end) }
    const common = { stream_id: f.stream_id, direction: f.direction, ...range }
    try {
      const [summary, colors, classes, events, series, status] = await Promise.all([
        get('/api/analytics/summary', { ...common, color: f.color, vehicle_class: f.vehicle_class }),
        get('/api/analytics/colors', { ...common, vehicle_class: f.vehicle_class }),
        get('/api/analytics/classes', { ...common, color: f.color }),
        get('/api/events', { ...common, color: f.color, vehicle_class: f.vehicle_class, limit: PAGE, offset: pageRef.current * PAGE }),
        get('/api/analytics/timeseries', { stream_id: f.stream_id, ...range, bucket: 'hour' }),
        get('/api/streams/status'),
      ])
      setData({ summary, colors, classes, events, series, status })
      setError(null)
      setLastUpdate(new Date())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Reload when filters/page change.
  useEffect(() => { setLoading(true); load() }, [filters, page, load])

  // Live updates: SSE pushes a refresh whenever a new event is persisted; poll as a fallback.
  useEffect(() => {
    let es
    let debounce
    try {
      es = new EventSource(liveUrl())
      es.onopen = () => setLive('live')
      es.onerror = () => setLive('reconnecting')
      es.addEventListener('crossing', () => { clearTimeout(debounce); debounce = setTimeout(load, 250) })
    } catch { setLive('polling') }
    const poll = setInterval(load, 5000)
    return () => { es && es.close(); clearInterval(poll); clearTimeout(debounce) }
  }, [load])

  const set = (k) => (e) => { setPage(0); setFilters((f) => ({ ...f, [k]: e.target.value })) }
  const s = data.summary
  const opts = (items) => (items?.items || []).map((i) => i.label)

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>Vehicle Analytics</h1>
          <p className="muted">Line-crossing counts from the DeepStream pipeline · all figures read from PostgreSQL</p>
        </div>
        <div className="right">
          <span className={`pill ${live}`}>{live === 'live' ? '● Live' : live === 'reconnecting' ? '◌ Reconnecting' : '○ ' + live}</span>
          <span className="muted small">{lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString()}` : ''}</span>
        </div>
      </header>

      {error && <div className="banner error" role="alert">API error — {error}. Showing last known data; retrying.</div>}

      <section className="filters" aria-label="Filters">
        <label>Stream<select value={filters.stream_id} onChange={set('stream_id')}>
          <option value="">All</option>
          {(data.status?.items || []).map((i) => <option key={i.stream_id}>{i.stream_id}</option>)}
        </select></label>
        <label>Color<select value={filters.color} onChange={set('color')}>
          <option value="">All</option>{opts(data.colors).filter((c) => c !== 'unknown').map((c) => <option key={c}>{c}</option>)}
        </select></label>
        <label>Class<select value={filters.vehicle_class} onChange={set('vehicle_class')}>
          <option value="">All</option>{opts(data.classes).map((c) => <option key={c}>{c}</option>)}
        </select></label>
        <label>Direction<select value={filters.direction} onChange={set('direction')}>
          <option value="">Both</option><option value="in">In</option><option value="out">Out</option>
        </select></label>
        <label>From<input type="datetime-local" value={filters.start} onChange={set('start')} /></label>
        <label>To<input type="datetime-local" value={filters.end} onChange={set('end')} /></label>
        <button className="ghost" onClick={() => { setPage(0); setFilters(EMPTY) }}>Reset</button>
      </section>

      <section className="cards">
        <Stat label="Total crossings" value={fmtNum(s?.total_crossings)} loading={loading && !s} />
        <Stat label="Unique vehicles" value={fmtNum(s?.unique_vehicles)} hint="distinct tracked vehicles" loading={loading && !s} />
        <Stat label="In / Out" value={s ? `${fmtNum(s.crossings_in)} / ${fmtNum(s.crossings_out)}` : '—'} loading={loading && !s} />
        <Stat label="Last hour" value={fmtNum(s?.crossings_last_hour)} loading={loading && !s} />
        <Stat label="Latest event" value={s?.last_event ? fmtTime(s.last_event) : '—'} small loading={loading && !s} />
      </section>

      <div className="grid">
        <Breakdown title="Vehicles by color" data={data.colors} color />
        <Breakdown title="Vehicles by class" data={data.classes} />
        <StatusPanel status={data.status} />
      </div>

      <div className="grid two">
        <Timeline series={data.series} />
        <LivePlayer />
      </div>

      <EventsTable data={data.events} loading={loading} page={page} pageSize={PAGE} onPage={setPage} />
    </div>
  )
}

function Stat({ label, value, hint, small, loading }) {
  return (
    <div className="card">
      <div className="muted small">{label}</div>
      <div className={`stat ${small ? 'sm' : ''} ${loading ? 'skeleton' : ''}`}>{loading ? ' ' : value}</div>
      {hint && <div className="muted tiny">{hint}</div>}
    </div>
  )
}
