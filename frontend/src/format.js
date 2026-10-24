export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString() : '—')
export const fmtPct = (v) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`)
export const fmtNum = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString())

/** Convert a <input type="datetime-local"> value to an ISO UTC string (or '' if empty). */
export function localToIso(v) {
  if (!v) return ''
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? '' : d.toISOString()
}

/** CSS colour for a classifier colour label; unknown labels fall back to grey. */
const COLORS = {
  black: '#1f2328', blue: '#2f6fed', brown: '#8b5a2b', gold: '#d4a017', green: '#2e9b4f',
  grey: '#8b949e', gray: '#8b949e', maroon: '#7b1f2b', orange: '#f08a24', red: '#e5484d',
  silver: '#c0c6cc', white: '#f4f4f5', yellow: '#f5d90a',
}
export const colorHex = (label) => COLORS[String(label || '').toLowerCase()] || '#5b6270'
