"""Pure-Python line-crossing logic (no GStreamer/pyds dependency, fully unit-testable).

A vehicle is represented by its tracker ID and an anchor point (bottom-centre of
its bounding box). A crossing is emitted when the anchor moves from one side of
the counting line to the other, with these guarantees:

* hysteresis: the anchor must leave a dead band of ``margin`` pixels on each side,
  so jitter around the line does not toggle state;
* once per (track, direction): a track that already produced an "in" event never
  produces another "in" event; a genuine reverse crossing produces one "out";
* the crossing must happen within the line segment (not on its infinite extension);
* state for tracks unseen for ``ttl_frames`` is evicted (bounded memory).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

UNTRACKED_ID = 0xFFFFFFFFFFFFFFFF  # DeepStream's UNTRACKED_OBJECT_ID


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    line_id: str = "line-1"

    def signed_distance(self, x: float, y: float) -> float:
        """Signed perpendicular distance; positive on the left of P1->P2 (image coords)."""
        dx, dy = self.x2 - self.x1, self.y2 - self.y1
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            raise ValueError("line has zero length")
        return (dx * (y - self.y1) - dy * (x - self.x1)) / length

    def projection(self, x: float, y: float) -> float:
        """Parameter t of the anchor's projection on the segment (0..1 inside)."""
        dx, dy = self.x2 - self.x1, self.y2 - self.y1
        return ((x - self.x1) * dx + (y - self.y1) * dy) / (dx * dx + dy * dy)


@dataclass
class _TrackState:
    side: int = 0                      # last confirmed side: -1, +1 or 0 (unknown)
    last_frame: int = 0
    counted: Set[str] = field(default_factory=set)


class LineCrossingDetector:
    """Stateful per-line detector. ``update`` returns "in", "out" or None."""

    def __init__(self, line: Line, margin: float = 4.0, ttl_frames: int = 150,
                 labels: Tuple[str, str] = ("in", "out")):
        self.line = line
        self.margin = margin
        self.ttl_frames = ttl_frames
        self.labels = labels  # (negative->positive, positive->negative)
        self._tracks: Dict[int, _TrackState] = {}

    def update(self, track_id: int, x: float, y: float, frame: int) -> Optional[str]:
        if track_id == UNTRACKED_ID:
            return None
        st = self._tracks.setdefault(track_id, _TrackState())
        st.last_frame = frame
        d = self.line.signed_distance(x, y)
        if abs(d) <= self.margin:          # inside the dead band: ignore
            return None
        side = 1 if d > 0 else -1
        if st.side == 0:
            st.side = side                 # first confident observation
            return None
        if side == st.side:
            return None
        previous, st.side = st.side, side
        if not 0.0 <= self.line.projection(x, y) <= 1.0:
            return None                    # went around the segment, not across it
        direction = self.labels[0] if previous < 0 else self.labels[1]
        if direction in st.counted:
            return None                    # duplicate protection
        st.counted.add(direction)
        return direction

    def evict_stale(self, frame: int) -> int:
        stale = [t for t, s in self._tracks.items() if frame - s.last_frame > self.ttl_frames]
        for t in stale:
            del self._tracks[t]
        return len(stale)

    def __len__(self) -> int:
        return len(self._tracks)


class AttributeBook:
    """Keeps the most confident colour/class seen for each track (survives occlusion)."""

    def __init__(self) -> None:
        self._color: Dict[int, Tuple[str, float]] = {}

    def observe_color(self, track_id: int, label: Optional[str], conf: float) -> None:
        if not label:
            return
        cur = self._color.get(track_id)
        if cur is None or conf >= cur[1]:
            self._color[track_id] = (label, conf)

    def color(self, track_id: int) -> Tuple[Optional[str], Optional[float]]:
        return self._color.get(track_id, (None, None))

    def forget(self, track_id: int) -> None:
        self._color.pop(track_id, None)
