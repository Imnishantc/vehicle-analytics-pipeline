import React, { useEffect, useRef, useState } from 'react'

/**
 * Bonus: live feed via MediaMTX HLS (set VITE_HLS_URL, e.g. http://localhost:8888/traffic/index.m3u8).
 * No boxes are drawn here. Bounding boxes only appear if VITE_HLS_URL points at a stream
 * rendered by DeepStream's OSD (see docs/setup.md, "Annotated stream"); the UI never fabricates them.
 */
export default function LivePlayer() {
  const url = import.meta.env?.VITE_HLS_URL
  const ref = useRef(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!url || !ref.current) return undefined
    const video = ref.current
    if (video.canPlayType('application/vnd.apple.mpegurl')) { video.src = url; return undefined }
    let hls
    let cancelled = false
    import('hls.js').then(({ default: Hls }) => {  // loaded lazily: only when a stream URL is configured
      if (cancelled) return
      if (!Hls.isSupported()) { setErr('HLS is not supported in this browser'); return }
      hls = new Hls({ liveSyncDurationCount: 3 })
      hls.loadSource(url)
      hls.attachMedia(video)
      hls.on(Hls.Events.ERROR, (_e, d) => { if (d.fatal) setErr(`Stream unavailable (${d.type})`) })
    })
    return () => { cancelled = true; if (hls) hls.destroy() }
  }, [url])

  return (
    <div className="panel">
      <h2>Live feed</h2>
      {!url && <div className="empty">Set <code>VITE_HLS_URL</code> to a MediaMTX HLS URL to embed the live stream.</div>}
      {url && <video ref={ref} controls muted autoPlay playsInline className="video" />}
      {err && <div className="small bad-text">{err}</div>}
    </div>
  )
}
