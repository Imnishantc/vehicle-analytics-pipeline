const BASE = import.meta.env?.VITE_API_BASE || ''

/** Build a query string, dropping empty values. */
export function qs(params = {}) {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') u.set(k, v)
  }
  const s = u.toString()
  return s ? `?${s}` : ''
}

export async function get(path, params) {
  const res = await fetch(`${BASE}${path}${qs(params)}`)
  if (!res.ok) {
    let detail = res.statusText
    try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* ignore */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

export const liveUrl = () => `${BASE}/api/live/events`
