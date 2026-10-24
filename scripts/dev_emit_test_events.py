"""DEV/TEST ONLY: pushes a few clearly-labelled synthetic events (source='test',
stream_id 'cam-devtest') through the real EventSink so the API/dashboard path can be
exercised without DeepStream. These are NOT detections. Delete with:
  DELETE FROM crossing_events WHERE source='test';
Usage: DATABASE_URL=... python scripts/dev_emit_test_events.py [count] [delay_s]
"""
import os
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "deepstream" / "src"))
from vds.events import CrossingEvent, EventSink, utcnow  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
delay = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
sink = EventSink(os.environ["DATABASE_URL"], "cam-devtest", "rtsp://localhost:8554/traffic")
sink.start()
sink.set_heartbeat("running", fps=0.0, frames=0, detail="synthetic test emitter (not DeepStream)")
colors = ["white", "black", "silver", "red", "blue", "grey"]
base = random.randint(1000, 10 ** 6)
for i in range(n):
    sink.submit(CrossingEvent("cam-devtest", sink.run_id, base + i, "Car", random.choice(["in", "out"]),
                              utcnow(), color=random.choice(colors), color_confidence=round(random.uniform(.6, .99), 2),
                              class_confidence=round(random.uniform(.5, .95), 2), source="test"))
    time.sleep(delay)
time.sleep(1)
sink.close()
print(f"emitted {n}, written={sink.written} dropped={sink.dropped} spooled={sink.spooled}")
