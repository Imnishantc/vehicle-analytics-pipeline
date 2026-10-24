"""DeepStream pipeline:

  nvurisrcbin (RTSP, auto-reconnect) -> nvstreammux -> nvinfer (PGIE, vehicles)
  -> nvtracker (NvDCF) -> nvinfer (SGIE, colour on vehicle crops) -> nvvideoconvert
  -> nvdsosd -> sink

A pad probe on the OSD sink pad extracts metadata, runs line-crossing logic and
hands events to the asynchronous ``EventSink``.

Requires NVIDIA DeepStream 7.x with the ``pyds`` bindings (Linux only). It has NOT
been executed on the development machine used to write this repo (Windows, no
DeepStream); see docs/testing.md for the validation status.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from typing import Optional

import yaml

from .crossing import AttributeBook, Line, LineCrossingDetector, UNTRACKED_ID
from .events import CrossingEvent, EventSink, utcnow

log = logging.getLogger("vds.pipeline")

PGIE_UID, SGIE_UID = 1, 2


class Pipeline:
    def __init__(self, cfg: dict, sink: EventSink):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import GLib, Gst
        self.Gst, self.GLib = Gst, GLib
        Gst.init(None)

        self.cfg, self.sink = cfg, sink
        # Support multiple independent counting lines. Keep the legacy
        # single-line configuration working when "lines" is not configured.
        line_configs = cfg.get("lines") or [cfg["line"]]
        self.detectors = []
        for index, ln in enumerate(line_configs, start=1):
            line = Line(
                ln["x1"], ln["y1"], ln["x2"], ln["y2"],
                ln.get("id", f"line-{index}")
            )
            self.detectors.append(LineCrossingDetector(
                line,
                margin=ln.get("margin", cfg.get("line", {}).get("margin", 4.0)),
                ttl_frames=ln.get(
                    "ttl_frames", cfg.get("line", {}).get("ttl_frames", 150)
                ),
                labels=tuple(ln.get(
                    "direction_labels",
                    cfg.get("line", {}).get("direction_labels", ["in", "out"])
                )),
            ))
        self.attrs = AttributeBook()
        self.vehicle_classes = set(cfg.get("vehicle_classes", ["Car"]))
        self.frames, self._fps_t0, self._fps_n, self.fps = 0, time.monotonic(), 0, 0.0
        self.loop = GLib.MainLoop()
        self.pipeline = self._build()

    # ------------------------------------------------------------------
    def _make(self, factory: str, name: str):
        el = self.Gst.ElementFactory.make(factory, name)
        if el is None:
            raise RuntimeError(f"Could not create GStreamer element '{factory}'")
        self.pipeline.add(el)
        return el

    def _build(self):
        Gst, c = self.Gst, self.cfg
        self.pipeline = Gst.Pipeline.new("vehicle-analytics")
        src = self._make("nvurisrcbin", "source")
        
        src.set_property("uri", c["rtsp_url"])

        # Prefer RTSP over TCP for a more reliable connection to MediaMTX.
        src.set_property("select-rtp-protocol", 4)

        # Reconnect after stream loss and allow buffering for network jitter.
        src.set_property("rtsp-reconnect-interval", int(c.get("reconnect_interval_s", 5)))
        src.set_property("latency", int(c.get("rtsp_latency_ms", 500)))



        mux = self._make("nvstreammux", "mux")
        mux.set_property("batch-size", 1)
        mux.set_property("width", c["mux"]["width"])
        mux.set_property("height", c["mux"]["height"])
        mux.set_property("live-source", 1)
        mux.set_property("batched-push-timeout", 40000)


        pgie = self._make("nvinfer", "pgie")
        pgie.set_property("config-file-path", c["pgie_config"])

        tracker = self._make("nvtracker", "tracker")
        self._configure_tracker(tracker, c["tracker"])

        enable_color = c.get("enable_color_classifier", True)
        sgie = None
        if enable_color:
            sgie = self._make("nvinfer", "sgie-color")
            sgie.set_property("config-file-path", c["sgie_config"])

        conv = self._make("nvvideoconvert", "conv")
        osd = self._make("nvdsosd", "osd")

        # Optional annotated RTSP output. When no URL is configured, retain
        # the original headless fakesink behavior.
        annotated_url = c.get("annotated_rtsp_url")
        output_elements = []
        if annotated_url:
            out_conv = self._make("nvvideoconvert", "out-conv")
            out_caps = self._make("capsfilter", "out-caps")
            out_caps.set_property(
                "caps", Gst.Caps.from_string(
                    "video/x-raw(memory:NVMM),format=NV12"
                )
            )
            encoder = self._make("nvv4l2h264enc", "h264-encoder")
            encoder.set_property("bitrate", int(c.get("output_bitrate", 4000000)))
            encoder.set_property("iframeinterval", int(c.get("output_iframe_interval", 30)))
            encoder.set_property("idrinterval", int(c.get("output_idr_interval", 30)))
            encoder.set_property("insert-sps-pps", True)
            parser = self._make("h264parse", "h264-parser")
            parser.set_property("config-interval", -1)
            sink = self._make("rtspclientsink", "rtsp-sink")
            sink.set_property("location", annotated_url)
            sink.set_property("protocols", 4)
            sink.set_property("latency", 200)
            output_elements = [out_conv, out_caps, encoder, parser, sink]
        else:
            sink = self._make(c.get("sink", "fakesink"), "sink")
            if sink.find_property("sync"):
                sink.set_property("sync", 0)
            if c.get("sink", "fakesink") == "fakesink":
                sink.set_property("enable-last-sample", 0)
            output_elements = [sink]

        # Link source to mux when its dynamic pad becomes available.
        src.connect("pad-added", self._on_pad_added, mux)

        elements = [mux, pgie, tracker]
        if sgie is not None:
            elements.append(sgie)
        elements.extend([conv, osd, *output_elements])

        for a, b in zip(elements, elements[1:]):
            if not a.link(b):
                raise RuntimeError(
                    f"Failed to link {a.get_name()} -> {b.get_name()}"
                )



        osd.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, self._probe)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus)
        return self.pipeline

    def _configure_tracker(self, tracker, t: dict) -> None:
        tracker.set_property("tracker-width", t.get("width", 640))
        tracker.set_property("tracker-height", t.get("height", 384))
        tracker.set_property("ll-lib-file", t.get("ll_lib", "/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so"))
        tracker.set_property("ll-config-file", t["config"])



    def _on_pad_added(self, _src, pad, mux):
       caps = pad.get_current_caps() or pad.query_caps(None)
       caps_text = caps.to_string() if caps else "NO CAPS"
       log.info("Source pad appeared: %s; caps=%s", pad.get_name(), caps_text)

       if not caps or not caps_text.startswith("video/x-raw"):
           log.warning("Ignoring non-raw-video source pad: %s", caps_text)
           return

       sinkpad = mux.get_static_pad("sink_0")
       if sinkpad is None:
           sinkpad = mux.request_pad_simple("sink_0")

       if sinkpad is None:
           log.error("Could not acquire nvstreammux sink_0 pad")
           return
       if sinkpad.is_linked():
           log.warning("nvstreammux sink_0 is already linked")
           return

       result = pad.link(sinkpad)
       if result != self.Gst.PadLinkReturn.OK:
           log.error("Source-to-mux link failed: %s", result)
       else:
           log.info("Source successfully linked to nvstreammux")

    def _on_bus(self, _bus, msg):
        Gst = self.Gst
        if msg.type == Gst.MessageType.EOS:
            log.warning("EOS received; stopping")
            self.sink.set_heartbeat("eos", self.fps, self.frames, detail="end of stream")
            self.loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            log.error("GStreamer error: %s (%s)", err, dbg)
            self.sink.set_heartbeat("error", self.fps, self.frames, detail=str(err))
            self.loop.quit()
        elif msg.type == Gst.MessageType.WARNING:
            log.warning("GStreamer warning: %s", msg.parse_warning()[0])

    # ------------------------------------------------------------------
    def _probe(self, _pad, info):
        import pyds
        buf = info.get_buffer()
        if not buf:
            return self.Gst.PadProbeReturn.OK
        batch = pyds.gst_buffer_get_nvds_batch_meta(hash(buf))
        l_frame = batch.frame_meta_list
        while l_frame is not None:
            fm = pyds.NvDsFrameMeta.cast(l_frame.data)
            self._handle_frame(pyds, fm)
            try:
                l_frame = l_frame.next
            except StopIteration:
                break
        return self.Gst.PadProbeReturn.OK

    def _handle_frame(self, pyds, fm) -> None:
        frame = fm.frame_num
        now = utcnow()
        self.frames += 1
        self._fps_n += 1
        t = time.monotonic()
        if t - self._fps_t0 >= 2.0:
            self.fps = self._fps_n / (t - self._fps_t0)
            self._fps_t0, self._fps_n = t, 0
            self.sink.set_heartbeat("running", self.fps, self.frames, now)
            for detector in self.detectors:
                detector.evict_stale(frame)


        l_obj = fm.obj_meta_list
        while l_obj is not None:
            obj = pyds.NvDsObjectMeta.cast(l_obj.data)
            try:
                l_next = l_obj.next
            except StopIteration:
                l_next = None
            tid = obj.object_id
            if tid != UNTRACKED_ID and obj.unique_component_id == PGIE_UID:
                self._read_color(pyds, obj, tid)
                if obj.obj_label in self.vehicle_classes:
                    r = obj.rect_params
                    anchor_x, anchor_y = r.left + r.width / 2.0, r.top + r.height  # bottom-centre
                    for detector in self.detectors:
                        direction = detector.update(
                            tid, anchor_x, anchor_y, frame
                        )
                        if direction:
                            color, cconf = self.attrs.color(tid)
                            self.sink.submit(CrossingEvent(
                                stream_id=self.sink.stream_id,
                                pipeline_run_id=self.sink.run_id,
                                vehicle_id=int(tid),
                                vehicle_class=obj.obj_label,
                                direction=direction,
                                event_time=now,
                                line_id=detector.line.line_id,
                                class_confidence=float(obj.confidence),
                                color=color,
                                color_confidence=cconf,
                                frame_number=int(frame),
                                bbox=(r.left, r.top, r.width, r.height),
                            ))
            l_obj = l_next

    def _read_color(self, pyds, obj, tid) -> None:
        l_cls = obj.classifier_meta_list
        while l_cls is not None:
            cm = pyds.NvDsClassifierMeta.cast(l_cls.data)
            if cm.unique_component_id == SGIE_UID:
                l_lbl = cm.label_info_list
                while l_lbl is not None:
                    li = pyds.NvDsLabelInfo.cast(l_lbl.data)
                    self.attrs.observe_color(tid, li.result_label, float(li.result_prob))
                    try:
                        l_lbl = l_lbl.next
                    except StopIteration:
                        break
            try:
                l_cls = l_cls.next
            except StopIteration:
                break

    # ------------------------------------------------------------------
    def run(self) -> int:
        Gst = self.Gst
        self.sink.set_heartbeat("starting")
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            log.error("pipeline failed to enter PLAYING")
            return 2
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.GLib.unix_signal_add(self.GLib.PRIORITY_HIGH, sig, self.loop.quit)
        try:
            self.loop.run()
        finally:
            self.pipeline.set_state(Gst.State.NULL)  # releases GPU/decoder resources
        return 0


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["rtsp_url"] = os.environ.get("RTSP_URL", cfg["rtsp_url"])
    return cfg


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="DeepStream vehicle analytics pipeline")
    ap.add_argument("--config", default=os.environ.get("VDS_CONFIG", "config/pipeline.yml"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log.error("DATABASE_URL is not set")
        return 1
    sink = EventSink(dsn, cfg.get("stream_id", "cam-1"), cfg["rtsp_url"],
                     spool_path=os.environ.get("SPOOL_PATH", "failed_events.jsonl"))
    sink.start()
    try:
        return Pipeline(cfg, sink).run()
    finally:
        sink.set_heartbeat("stopped")
        time.sleep(0.2)
        sink.close()


if __name__ == "__main__":
    sys.exit(main())
