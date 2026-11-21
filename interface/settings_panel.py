"""Right-hand control panel: effect parameters, studio, camera/tracking, recording, gestures."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QScrollArea, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from core.gesture_recognition import GESTURE_LABELS, GESTURES
from core.interaction_manager import ACTIONS
from effects.presets import PRESETS, PRESET_NAMES
from interface import theme
from interface.widgets import ColorButton, LabeledSlider, Row, SegmentedControl, ToggleSwitch, section


def scroll_wrap(widget: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    s.setWidget(widget)
    return s


# =========================================================================== effect params
class ParamsTab(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.effect = None
        self.action_cb = None
        self._controls: dict = {}
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 8, 8, 8)
        self.lay.setSpacing(6)
        self._build_empty()

    def _clear(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
        self._controls = {}

    def _clear_layout(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _build_empty(self):
        lab = QLabel("Select an effect in the library to customise it.")
        lab.setObjectName("muted")
        lab.setWordWrap(True)
        self.lay.addWidget(lab)
        self.lay.addStretch()

    def set_effect(self, effect, on_toggle):
        self._clear()
        self.effect = effect
        self._on_toggle = on_toggle
        if effect is None:
            self._build_empty()
            return
        head = QHBoxLayout()
        name = QLabel(effect.name)
        name.setObjectName("h1")
        head.addWidget(name)
        head.addStretch()
        self.switch = ToggleSwitch(effect.enabled)
        self.switch.toggled.connect(lambda on: on_toggle(effect, on))
        head.addWidget(self.switch)
        self.lay.addLayout(head)
        chip = QLabel(effect.category)
        chip.setObjectName("chip")
        chip.setFixedHeight(20)
        row = QHBoxLayout()
        row.addWidget(chip)
        row.addStretch()
        self.lay.addLayout(row)
        desc = QLabel(effect.description)
        desc.setWordWrap(True)
        desc.setObjectName("muted")
        self.lay.addWidget(desc)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.lay.addWidget(self.status)
        self.error = QLabel("")
        self.error.setStyleSheet(f"color:{theme.RED};")
        self.error.setWordWrap(True)
        self.lay.addWidget(self.error)
        self.status.setVisible(False)
        self.error.setVisible(False)

        if effect.id == "filter_frame":
            self.lay.addWidget(section("Pinned frames"))
            row = QHBoxLayout()
            for label, action in (("Pin now  (Space)", "pin_frame"), ("Remove last", "remove_last_pin"),
                                  ("Clear all", "clear_pins")):
                b = QPushButton(label)
                b.clicked.connect(lambda _=False, a=action: self.action_cb and self.action_cb(a))
                row.addWidget(b)
            self.lay.addLayout(row)
            tip = QLabel("Hold the frame still ~1 s or quick-pinch one hand to pin it. Pinch inside a "
                         "pinned frame to move it, point at it to change its filter, hold two fists to clear.")
            tip.setObjectName("dim")
            tip.setWordWrap(True)
            self.lay.addWidget(tip)
        self.lay.addWidget(section("Settings"))
        for p in effect.PARAMS:
            w = self._make_control(effect, p)
            self.lay.addWidget(w)
        self.lay.addWidget(section("Layer"))
        order = QSpinBox()
        order.setRange(0, 300)
        order.setValue(effect.order)
        order.setFixedWidth(80)
        order.valueChanged.connect(lambda v: (setattr(effect, "order", v), self.changed.emit()))
        self.lay.addWidget(Row("Layer order (higher = drawn on top)", order))
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset)
        self.lay.addWidget(reset)
        self.lay.addStretch()

    def _make_control(self, effect, p):
        cur = effect.params[p.key]
        if p.kind in ("float", "int"):
            w = LabeledSlider(p.label, p.min, p.max, cur, p.step if p.kind == "float" else max(1, p.step),
                              decimals=0 if p.kind == "int" else None, tip=p.tip)
            w.valueChanged.connect(lambda v, k=p.key: self._set(k, v))
        elif p.kind == "bool":
            sw = ToggleSwitch(bool(cur))
            sw.toggled.connect(lambda v, k=p.key: self._set(k, v))
            w = Row(p.label, sw, p.tip)
            w.ctrl = sw
        elif p.kind == "color":
            b = ColorButton(cur)
            b.colorChanged.connect(lambda v, k=p.key: self._set(k, v))
            w = Row(p.label, b, p.tip)
            w.ctrl = b
        else:
            cb = QComboBox()
            cb.addItems(list(p.choices))
            cb.setCurrentText(str(cur))
            cb.setMinimumWidth(150)
            cb.currentTextChanged.connect(lambda v, k=p.key: self._set(k, v))
            w = Row(p.label, cb, p.tip)
            w.ctrl = cb
        self._controls[p.key] = (p, w)
        return w

    def _set(self, key, value):
        if self.effect is not None:
            self.effect.set_param(key, value)
            self.changed.emit()

    def _reset(self):
        if self.effect:
            self.effect.reset_params()
            self.effect.on_param_changed("filter") if "filter" in self.effect.params else None
            self.refresh_values(force=True)
            self.changed.emit()

    def refresh_values(self, force=False):
        """Reflect parameter changes made by gestures / presets."""
        e = self.effect
        if e is None:
            return
        self.switch.set_silent(e.enabled)
        self.status.setText(e.status)
        self.status.setVisible(bool(e.status))
        self.error.setText(f"Error: {e.error}" if e.error else "")
        self.error.setVisible(bool(e.error))
        for key, (p, w) in self._controls.items():
            v = e.params[key]
            if p.kind in ("float", "int"):
                if force or abs(w.value() - v) > 1e-6 and not w.slider.isSliderDown():
                    w.set_value(v, silent=True)
            elif p.kind == "bool":
                if w.ctrl.isChecked() != bool(v):
                    w.ctrl.set_silent(bool(v))
            elif p.kind == "color":
                if w.ctrl.color() != v:
                    w.ctrl.set_color(v)
            else:
                if w.ctrl.currentText() != str(v):
                    w.ctrl.blockSignals(True)
                    w.ctrl.setCurrentText(str(v))
                    w.ctrl.blockSignals(False)


# =========================================================================== studio
class StudioTab(QWidget):
    preset_selected = Signal(str)
    render_changed = Signal()
    order_changed = Signal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        rs = engine.settings.render
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(section("Preset"))
        self.preset = QComboBox()
        self.preset.addItems(PRESET_NAMES)
        self.preset.setCurrentText(engine.preset)
        self.preset.currentTextChanged.connect(self._preset)
        lay.addWidget(self.preset)
        self.preset_desc = QLabel(PRESETS.get(engine.preset, {}).get("desc", ""))
        self.preset_desc.setObjectName("muted")
        self.preset_desc.setWordWrap(True)
        lay.addWidget(self.preset_desc)

        lay.addWidget(section("Look"))
        self.intensity = LabeledSlider("Master intensity", 0, 1.5, rs.master_intensity, 0.01)
        self.intensity.valueChanged.connect(lambda v: self._set("master_intensity", v))
        lay.addWidget(self.intensity)
        self.dim = LabeledSlider("Darken background", 0, 1, rs.background_dim, 0.01)
        self.dim.valueChanged.connect(lambda v: self._set("background_dim", v))
        lay.addWidget(self.dim)
        self.bloom = LabeledSlider("Glow (bloom)", 0, 2.5, rs.bloom, 0.01)
        self.bloom.valueChanged.connect(lambda v: self._set("bloom", v))
        lay.addWidget(self.bloom)
        self.cam = ToggleSwitch(rs.show_camera)
        self.cam.toggled.connect(lambda v: self._set("show_camera", v))
        lay.addWidget(Row("Show camera image", self.cam, "Turn off for effects on pure black"))
        self.quality = SegmentedControl(("low", "medium", "high"), rs.quality)
        self.quality.changed.connect(lambda v: self._set("quality", v))
        lay.addWidget(Row("Render quality", self.quality))

        lay.addWidget(section("Active layers  (top = drawn last)"))
        self.layers = QListWidget()
        self.layers.setMinimumHeight(170)
        lay.addWidget(self.layers)
        btns = QHBoxLayout()
        up, down = QPushButton("Move up"), QPushButton("Move down")
        up.clicked.connect(lambda: self._move(1))
        down.clicked.connect(lambda: self._move(-1))
        btns.addWidget(up)
        btns.addWidget(down)
        lay.addLayout(btns)
        hint = QLabel("Image effects (distortion, filters, colour) are applied in order, then "
                      "overlays (skeleton, particles, energy) are drawn on top in order.")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch()
        self.refresh_layers()

    def _preset(self, name):
        self.preset_desc.setText(PRESETS.get(name, {}).get("desc", ""))
        self.preset_selected.emit(name)

    def sync(self):
        rs = self.engine.settings.render
        self.preset.blockSignals(True)
        self.preset.setCurrentText(self.engine.preset)
        self.preset.blockSignals(False)
        self.preset_desc.setText(PRESETS.get(self.engine.preset, {}).get("desc", ""))
        self.intensity.set_value(rs.master_intensity, silent=True)
        self.dim.set_value(rs.background_dim, silent=True)
        self.bloom.set_value(rs.bloom, silent=True)
        self.cam.set_silent(rs.show_camera)
        self.refresh_layers()

    def _set(self, key, v):
        setattr(self.engine.settings.render, key, v)
        self.render_changed.emit()

    def refresh_layers(self):
        sel = self.layers.currentItem().data(Qt.UserRole) if self.layers.currentItem() else None
        self.layers.clear()
        for e in sorted(self.engine.active_effects(), key=lambda e: -e.order):
            kind = ("image + overlay" if e.uses_image and e.uses_overlay else "image" if e.uses_image else "overlay")
            it = QListWidgetItem(f"{e.name}    ·  {kind}  ·  {e.order}")
            it.setData(Qt.UserRole, e.id)
            self.layers.addItem(it)
            if e.id == sel:
                self.layers.setCurrentItem(it)

    def _move(self, direction):
        it = self.layers.currentItem()
        if not it:
            return
        active = sorted(self.engine.active_effects(), key=lambda e: -e.order)
        ids = [e.id for e in active]
        i = ids.index(it.data(Qt.UserRole))
        j = i - direction
        if not 0 <= j < len(active):
            return
        a, b = active[i], active[j]
        if a.order == b.order:
            b.order += direction
        a.order, b.order = b.order, a.order
        self.refresh_layers()
        self.order_changed.emit()


# =========================================================================== camera & tracking
class CameraTab(QWidget):
    restart_requested = Signal()
    tracking_changed = Signal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        cs, ts = engine.settings.camera, engine.settings.tracking
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(section("Camera"))
        self.cam = QComboBox()
        self.cam.addItem(f"Camera {cs.index}", cs.index)
        scan = QPushButton("Detect")
        scan.clicked.connect(self._scan)
        r = QHBoxLayout()
        r.addWidget(self.cam, 1)
        r.addWidget(scan)
        lay.addLayout(r)
        self.res = QComboBox()
        for w, h in ((640, 480), (1280, 720), (1920, 1080)):
            self.res.addItem(f"{w} × {h}", (w, h))
        self.res.setCurrentText(f"{cs.width} × {cs.height}")
        lay.addWidget(Row("Resolution", self.res))
        self.mirror = ToggleSwitch(cs.mirror)
        lay.addWidget(Row("Mirror (selfie view)", self.mirror))
        apply = QPushButton("Apply camera settings")
        apply.setObjectName("accent")
        apply.clicked.connect(self._apply)
        lay.addWidget(apply)

        lay.addWidget(section("Hand tracking"))
        self.smooth = LabeledSlider("Smoothing", 0, 1, ts.smoothing, 0.01,
                                    tip="Higher = steadier but slightly laggier. Lower = snappier.")
        self.smooth.valueChanged.connect(self._smoothing)
        lay.addWidget(self.smooth)
        self.det = LabeledSlider("Detection sensitivity", 0.2, 0.9, 1.1 - ts.detection_confidence, 0.01,
                                 tip="Higher finds hands more easily but may produce false detections.")
        lay.addWidget(self.det)
        self.trk = LabeledSlider("Tracking confidence", 0.2, 0.9, ts.tracking_confidence, 0.01)
        lay.addWidget(self.trk)
        self.det.slider.sliderReleased.connect(self._conf)
        self.trk.slider.sliderReleased.connect(self._conf)
        self.hands = SegmentedControl(("1", "2"), str(ts.max_hands))
        lay.addWidget(Row("Max hands", self.hands))
        self.hands.changed.connect(lambda v: (setattr(ts, "max_hands", int(v)), self.restart_requested.emit()))
        self.proc = QComboBox()
        for wv, lab in ((320, "Fast (320 px)"), (480, "Balanced (480 px)"), (640, "Accurate (640 px)"), (800, "Max (800 px)")):
            self.proc.addItem(lab, wv)
        idx = max(0, [320, 480, 640, 800].index(ts.process_width) if ts.process_width in (320, 480, 640, 800) else 2)
        self.proc.setCurrentIndex(idx)
        self.proc.currentIndexChanged.connect(self._proc)
        lay.addWidget(Row("Tracking resolution", self.proc))
        self.low = ToggleSwitch(ts.low_light)
        self.low.toggled.connect(self._lowlight)
        lay.addWidget(Row("Low-light boost", self.low, "Improves tracking in dark or backlit rooms"))
        self.grace = LabeledSlider("Keep lost hands for (s)", 0.0, 1.0, ts.lost_grace, 0.05)
        self.grace.valueChanged.connect(self._grace)
        lay.addWidget(self.grace)
        lay.addWidget(section("Live stats"))
        self.stats = QLabel("—")
        self.stats.setObjectName("muted")
        self.stats.setWordWrap(True)
        lay.addWidget(self.stats)
        tip = QLabel("Tips: face a light source, avoid a bright window behind you, keep hands "
                     "50–150 cm from the camera and fully in view.")
        tip.setObjectName("dim")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch()

    def _scan(self):
        from core.camera import list_cameras
        self.cam.clear()
        self.cam.addItem("Scanning...", -1)
        self.cam.repaint()
        was_running = self.engine.camera is not None
        if was_running:
            self.engine.camera.stop()
        found = list_cameras()
        self.cam.clear()
        for i in found or [self.engine.settings.camera.index]:
            self.cam.addItem(f"Camera {i}", i)
        cur = self.engine.settings.camera.index
        for k in range(self.cam.count()):
            if self.cam.itemData(k) == cur:
                self.cam.setCurrentIndex(k)
        if was_running:
            self.restart_requested.emit()

    def _apply(self):
        cs = self.engine.settings.camera
        idx = self.cam.currentData()
        if idx is not None and idx >= 0:
            cs.index = int(idx)
        cs.width, cs.height = self.res.currentData()
        cs.mirror = self.mirror.isChecked()
        self.restart_requested.emit()

    def _smoothing(self, v):
        self.engine.settings.tracking.smoothing = v
        if self.engine.tracker:
            self.engine.tracker.set_smoothing(v)

    def _conf(self):
        ts = self.engine.settings.tracking
        ts.detection_confidence = round(1.1 - self.det.value(), 2)
        ts.tracking_confidence = round(self.trk.value(), 2)
        if self.engine.tracker:
            self.engine.tracker.set_confidence(ts.detection_confidence, ts.tracking_confidence)

    def _proc(self, _):
        v = self.proc.currentData()
        self.engine.settings.tracking.process_width = v
        if self.engine.tracker:
            self.engine.tracker.process_width = v

    def _lowlight(self, on):
        self.engine.settings.tracking.low_light = on
        if self.engine.tracker:
            self.engine.tracker.low_light_boost = on

    def _grace(self, v):
        self.engine.settings.tracking.lost_grace = v
        if self.engine.tracker:
            self.engine.tracker.lost_grace = v

    def update_stats(self):
        e = self.engine
        cam = e.camera
        trk = e.tracker
        tr = e.last_tracking
        lines = []
        if cam:
            lines.append(f"Camera: {cam.width}×{cam.height} @ {cam.measured_fps:.0f} FPS")
        if trk:
            inf = tr.inference_ms if tr else 0
            lines.append(f"Tracking: {trk.fps:.0f} FPS · {inf:.0f} ms per frame")
        lines.append(f"Render: {e.stats['render_ms']:.1f} ms · effects {e.stats['update_ms']:.1f} ms")
        lines.append(f"Hands: {e.stats['hands']}")
        self.stats.setText("\n".join(lines))


# =========================================================================== recording
class RecordTab(QWidget):
    record_clicked = Signal()
    screenshot_clicked = Signal()
    guide_changed = Signal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        rs = engine.settings.recording
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(section("Format"))
        self.fmt = SegmentedControl(("16:9", "9:16", "1:1"), rs.format if rs.format in ("16:9", "9:16", "1:1") else "16:9")
        self.fmt.changed.connect(self._fmt)
        lay.addWidget(self.fmt)
        fmt_hint = QLabel("9:16 = vertical for TikTok / Reels / Shorts. 16:9 = YouTube.")
        fmt_hint.setObjectName("dim")
        lay.addWidget(fmt_hint)
        self.res = SegmentedControl(("720p", "1080p"), f"{rs.resolution}p" if rs.resolution in (720, 1080) else "1080p")
        self.res.changed.connect(lambda v: setattr(rs, "resolution", int(v[:-1])))
        lay.addWidget(Row("Resolution", self.res))
        self.fps = SegmentedControl(("24", "30", "60"), str(rs.fps) if rs.fps in (24, 30, 60) else "30")
        self.fps.changed.connect(lambda v: setattr(rs, "fps", int(v)))
        lay.addWidget(Row("Frame rate", self.fps))
        self.quality = LabeledSlider("Quality", 0, 100, int((30 - rs.quality) / 14 * 100), 1, decimals=0, suffix="%")
        self.quality.valueChanged.connect(lambda v: setattr(rs, "quality", int(round(30 - v / 100 * 14))))
        lay.addWidget(self.quality)
        self.smart = ToggleSwitch(True)
        lay.addWidget(Row("Smart framing (follow hands)", self.smart,
                          "In 9:16 and 1:1, the crop window glides to keep your hands in shot."))
        self.guide = ToggleSwitch(True)
        self.guide.toggled.connect(lambda _: self.guide_changed.emit())
        lay.addWidget(Row("Show crop guide in preview", self.guide))

        lay.addWidget(section("Cinematic HUD"))
        self.hud = ToggleSwitch(rs.hud)
        self.hud.toggled.connect(lambda v: setattr(rs, "hud", bool(v)))
        lay.addWidget(Row("Sci-fi HUD in recordings", self.hud,
                          "Overlays live tracking data, reticles, timecode, system stats and an event log "
                          "on the video. Shown in the preview while recording."))
        from interface.hud import DETAILS, STYLE_NAMES
        self.hud_style = SegmentedControl(tuple(STYLE_NAMES), rs.hud_style if rs.hud_style in STYLE_NAMES else "Cyber")
        self.hud_style.changed.connect(lambda v: setattr(rs, "hud_style", v))
        lay.addWidget(Row("Style", self.hud_style))
        self.hud_detail = SegmentedControl(tuple(DETAILS), rs.hud_detail if rs.hud_detail in DETAILS else "Full")
        self.hud_detail.changed.connect(lambda v: setattr(rs, "hud_detail", v))
        lay.addWidget(Row("Detail", self.hud_detail))
        self.hud_always = ToggleSwitch(rs.hud_always)
        self.hud_always.toggled.connect(lambda v: setattr(rs, "hud_always", bool(v)))
        lay.addWidget(Row("Show HUD when not recording", self.hud_always))
        self.countdown = ToggleSwitch(rs.countdown)
        self.countdown.toggled.connect(lambda v: setattr(rs, "countdown", bool(v)))
        lay.addWidget(Row("3-2-1 countdown before recording", self.countdown))

        lay.addWidget(section("Output folder"))
        self.dir_label = QLabel(rs.output_dir)
        self.dir_label.setObjectName("muted")
        self.dir_label.setWordWrap(True)
        lay.addWidget(self.dir_label)
        r = QHBoxLayout()
        browse = QPushButton("Change...")
        browse.clicked.connect(self._browse)
        opn = QPushButton("Open folder")
        opn.clicked.connect(lambda: self._open(rs.output_dir))
        r.addWidget(browse)
        r.addWidget(opn)
        lay.addLayout(r)

        lay.addWidget(section("Capture"))
        self.rec_btn = QPushButton("●  Start recording   (R)")
        self.rec_btn.setObjectName("rec")
        self.rec_btn.setMinimumHeight(44)
        self.rec_btn.clicked.connect(self.record_clicked.emit)
        lay.addWidget(self.rec_btn)
        self.rec_info = QLabel("")
        self.rec_info.setObjectName("muted")
        lay.addWidget(self.rec_info)
        shot = QPushButton("📷  Screenshot   (P)")
        shot.clicked.connect(self.screenshot_clicked.emit)
        lay.addWidget(shot)

        lay.addWidget(section("Last recording"))
        self.last_thumb = QLabel()
        self.last_thumb.setFixedHeight(150)
        self.last_thumb.setAlignment(Qt.AlignCenter)
        self.last_thumb.setStyleSheet(f"background:{theme.CARD}; border-radius:10px; color:{theme.DIM};")
        self.last_thumb.setText("Nothing recorded yet")
        lay.addWidget(self.last_thumb)
        self.last_label = QLabel("")
        self.last_label.setObjectName("dim")
        self.last_label.setWordWrap(True)
        lay.addWidget(self.last_label)
        r2 = QHBoxLayout()
        self.play = QPushButton("▶  Play")
        self.play.setEnabled(False)
        self.play.clicked.connect(lambda: self._open(self._last_path))
        self.show_btn = QPushButton("Show in folder")
        self.show_btn.setEnabled(False)
        self.show_btn.clicked.connect(self._reveal)
        r2.addWidget(self.play)
        r2.addWidget(self.show_btn)
        lay.addLayout(r2)
        lay.addStretch()
        self._last_path = None

    def _fmt(self, v):
        self.engine.settings.recording.format = v
        self.guide_changed.emit()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder", self.engine.settings.recording.output_dir)
        if d:
            self.engine.settings.recording.output_dir = d
            self.dir_label.setText(d)

    @staticmethod
    def _open(path):
        if path:
            os.makedirs(path, exist_ok=True) if not os.path.splitext(path)[1] else None
            os.startfile(path)  # noqa: S606 - opens with the default Windows app

    def _reveal(self):
        if self._last_path:
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self._last_path)])

    def set_recording(self, on: bool):
        self.rec_btn.setProperty("recording", "true" if on else "false")
        self.rec_btn.setText("■  Stop recording   (R)" if on else "●  Start recording   (R)")
        self.rec_btn.style().unpolish(self.rec_btn)
        self.rec_btn.style().polish(self.rec_btn)
        for w in (self.fmt, self.res, self.fps):
            w.setEnabled(not on)

    def set_last(self, info, thumb_rgb=None):
        self._last_path = info.path
        self.play.setEnabled(True)
        self.show_btn.setEnabled(True)
        m, s = divmod(int(info.duration), 60)
        size = os.path.getsize(info.path) / 1e6 if os.path.exists(info.path) else 0
        self.last_label.setText(f"{os.path.basename(info.path)}\n{info.width}×{info.height} · {info.fps} FPS · "
                                f"{m:02d}:{s:02d} · {size:.1f} MB")
        if thumb_rgb is not None:
            from PySide6.QtGui import QImage
            import cv2
            h, w = thumb_rgb.shape[:2]
            s_ = min(300 / w, 150 / h)
            t = cv2.resize(thumb_rgb, (int(w * s_), int(h * s_)), interpolation=cv2.INTER_AREA)
            t = t.copy()
            qi = QImage(t.data, t.shape[1], t.shape[0], 3 * t.shape[1], QImage.Format_RGB888).copy()
            self.last_thumb.setPixmap(QPixmap.fromImage(qi))


# =========================================================================== gestures
class GesturesTab(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(section("Live readout"))
        self.hand_widgets = []
        for side in ("Left", "Right"):
            box = QFrame()
            box.setStyleSheet(f"QFrame {{ background:{theme.CARD}; border-radius:10px; }}")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            title = QLabel(f"{side} hand")
            title.setObjectName("h2")
            title.setStyleSheet(f"color:{theme.CYAN if side == 'Left' else theme.MAGENTA}; background:transparent;")
            g = QLabel("—")
            g.setStyleSheet("background:transparent;")
            bl.addWidget(title)
            bl.addWidget(g)
            bars = {}
            for k in ("pinch", "spread", "openness"):
                row = QHBoxLayout()
                lab = QLabel(k.capitalize())
                lab.setObjectName("dim")
                lab.setFixedWidth(64)
                lab.setStyleSheet("background:transparent;")
                pb = QProgressBar()
                pb.setRange(0, 100)
                pb.setTextVisible(False)
                pb.setFixedHeight(6)
                row.addWidget(lab)
                row.addWidget(pb)
                bl.addLayout(row)
                bars[k] = pb
            lay.addWidget(box)
            self.hand_widgets.append((side, g, bars))
        self.two = QLabel("Two-hand distance: —")
        self.two.setObjectName("muted")
        lay.addWidget(self.two)

        lay.addWidget(section("Gesture shortcuts"))
        self.enabled = ToggleSwitch(engine.interaction.enabled)
        self.enabled.toggled.connect(lambda v: setattr(engine.interaction, "enabled", v))
        lay.addWidget(Row("Enable gesture shortcuts", self.enabled))
        for b in engine.interaction.bindings:
            cb = QComboBox()
            for key, lab in ACTIONS.items():
                cb.addItem(lab, key)
            cb.setCurrentIndex(list(ACTIONS).index(b.action) if b.action in ACTIONS else 0)
            cb.currentIndexChanged.connect(lambda _, b=b, cb=cb: setattr(b, "action", cb.currentData()))
            lay.addWidget(Row(f"Hold {GESTURE_LABELS.get(b.gesture, b.gesture)} ({b.hold:.1f}s)", cb))
        lay.addWidget(section("How to play"))
        guide = QLabel(
            "• <b>L-shape with both hands</b> – Filter Frame / Glass Prism lens<br>"
            "• <b>Touch fingertips together</b> – close the frame → next filter<br>"
            "• <b>Pinch</b> – lens bubble, plasma orb, gather particles<br>"
            "• <b>Open palm</b> – energy field, portal, push particles away<br>"
            "• <b>Close fist</b> – shockwave + particle explosion<br>"
            "• <b>Hands together</b> – big shockwave<br>"
            "• <b>Hands apart</b> – grow portals and 3D geometry<br>"
            "• <b>Rotate wrist</b> – spin kaleidoscope, twist space, shift hue<br>"
            "• <b>Point both index fingers</b> – energy beam<br>"
            "• <b>Peace sign</b> – jump colour palette<br>"
            "• <b>Move fast</b> – energy trails, RGB split")
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.RichText)
        guide.setObjectName("muted")
        lay.addWidget(guide)
        lay.addStretch()

    def update_live(self):
        gf = self.engine.last_gestures
        tr = self.engine.last_tracking
        by_label = {}
        if gf and tr:
            for h in tr.hands:
                g = gf.hands.get(h.hand_id)
                if g:
                    by_label[h.label] = g
        for side, lab, bars in self.hand_widgets:
            g = by_label.get(side)
            if g is None:
                lab.setText("not visible")
                for pb in bars.values():
                    pb.setValue(0)
                continue
            lab.setText(f"{GESTURE_LABELS.get(g.gesture, g.gesture)}   (held {g.hold_time:.1f}s)")
            bars["pinch"].setValue(int(g.pinch * 100))
            bars["spread"].setValue(int(g.spread * 100))
            bars["openness"].setValue(int(g.openness * 100))
        if gf and gf.two_hand.get("active", 0) > 0:
            self.two.setText(f"Two-hand distance: {gf.two_hand['distance_norm'] * 100:.0f}%  ·  "
                             f"together {gf.two_hand['together'] * 100:.0f}%")
        else:
            self.two.setText("Two-hand distance: — (show both hands)")


class SettingsPanel(QFrame):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 4, 8)
        self.tabs = QTabWidget()
        self.params = ParamsTab()
        self.studio = StudioTab(engine)
        self.camera = CameraTab(engine)
        self.record = RecordTab(engine)
        self.gestures = GesturesTab(engine)
        self.tabs.addTab(scroll_wrap(self.params), "Effect")
        self.tabs.addTab(scroll_wrap(self.studio), "Studio")
        self.tabs.addTab(scroll_wrap(self.record), "Record")
        self.tabs.addTab(scroll_wrap(self.camera), "Camera")
        self.tabs.addTab(scroll_wrap(self.gestures), "Gestures")
        lay.addWidget(self.tabs)
