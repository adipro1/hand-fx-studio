"""HAND FX STUDIO main window."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QIcon, QKeySequence, QLinearGradient, QPainter, QPen,
                           QPixmap, QShortcut)
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QSizePolicy, QStatusBar, QVBoxLayout, QWidget)

from core.engine import Engine
from effects.presets import PRESET_NAMES
from interface import theme
from interface.effects_panel import EffectsPanel
from interface.preview import PreviewWidget
from interface.settings_panel import SettingsPanel
from interface.widgets import LabeledSlider
from recording.recorder import Recorder

log = logging.getLogger("hfx.ui")


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 64, 64)
    g.setColorAt(0, QColor(theme.CYAN))
    g.setColorAt(1, QColor(theme.MAGENTA))
    p.setBrush(QColor("#0b0e15"))
    p.setPen(QPen(g, 3))
    p.drawRoundedRect(QRectF(3, 3, 58, 58), 14, 14)
    p.setPen(QPen(g, 4, Qt.SolidLine, Qt.RoundCap))
    for x, top in ((20, 18), (28, 13), (36, 15), (44, 21)):
        p.drawLine(QPointF(x, top), QPointF(x, 40))
    p.drawLine(QPointF(14, 32), QPointF(20, 42))
    p.drawArc(QRectF(17, 30, 30, 22), 180 * 16, 180 * 16)
    p.end()
    return QIcon(pm)


class Logo(QWidget):
    """Icon + wordmark. Built from labels so Qt sizes it correctly at any DPI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(make_icon().pixmap(28, 28))
        lay.addWidget(icon)
        f = QFont(theme.FONT.split(",")[0], 13)
        f.setWeight(QFont.Bold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2.5)
        hand = QLabel("HAND FX")
        hand.setFont(f)
        studio = QLabel("STUDIO")
        studio.setFont(f)
        studio.setStyleSheet(f"color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {theme.CYAN}, "
                             f"stop:1 {theme.MAGENTA});")
        for lab in (hand, studio):   # Qt's size hint ignores letter-spacing; add it back
            lab.setMinimumWidth(lab.sizeHint().width() + int(3 * len(lab.text())) + 4)
        lay.addWidget(hand)
        lay.addSpacing(4)
        lay.addWidget(studio)


class _Bridge(QObject):
    started = Signal(object)   # error message or None


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.engine = Engine(settings)
        self.engine.action_callback = self._on_action
        self.recorder = Recorder()
        self._last_frame: np.ndarray | None = None
        self._frames = 0
        self._fps_t = time.perf_counter()
        self._fps = 0.0
        self._clean = False
        self._thumb_time: dict[str, float] = {}
        self._starting = False
        self._bridge = _Bridge()
        self._bridge.started.connect(self._on_started)

        self.setWindowTitle("HAND FX STUDIO")
        self.setWindowIcon(make_icon())
        from PySide6.QtGui import QGuiApplication
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.compact = avail.width() < 1700
        self.resize(min(1600, int(avail.width() * 0.94)), min(940, int(avail.height() * 0.92)))
        self.setMinimumSize(1000, 640)
        self._build()
        self._shortcuts()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._ui_update)
        self.ui_timer.start(250)
        QTimer.singleShot(80, self._start_engine)

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(58)
        th = QHBoxLayout(top)
        th.setContentsMargins(16, 8, 16, 8)
        th.setSpacing(10)
        th.addWidget(Logo())
        th.addSpacing(20)
        lab = QLabel("Preset")
        lab.setObjectName("muted")
        th.addWidget(lab)
        self.preset_box = QComboBox()
        self.preset_box.addItems(PRESET_NAMES)
        self.preset_box.setCurrentText(self.engine.preset)
        self.preset_box.setMinimumWidth(180)
        self.preset_box.currentTextChanged.connect(self._apply_preset)
        th.addWidget(self.preset_box)
        prev_b = QPushButton("‹")
        prev_b.setObjectName("ghost")
        prev_b.setFixedWidth(34)
        prev_b.setToolTip("Previous preset (←)")
        prev_b.clicked.connect(lambda: self._cycle_preset(-1))
        next_b = QPushButton("›")
        next_b.setObjectName("ghost")
        next_b.setFixedWidth(34)
        next_b.setToolTip("Next preset (→)")
        next_b.clicked.connect(lambda: self._cycle_preset(1))
        th.addWidget(prev_b)
        th.addWidget(next_b)
        th.addSpacing(16)
        self.intensity = LabeledSlider("Intensity", 0, 1.5, self.settings.render.master_intensity, 0.01)
        self.intensity.setFixedWidth(170 if self.compact else 200)
        self.intensity.valueChanged.connect(self._set_intensity)
        th.addWidget(self.intensity)
        th.addSpacing(16)
        th.addStretch()
        self.clean_btn = QPushButton("Clean view  (Tab)")
        self.clean_btn.setObjectName("ghost")
        self.clean_btn.clicked.connect(self.toggle_clean)
        th.addWidget(self.clean_btn)
        shot = QPushButton("Screenshot")
        shot.clicked.connect(self.screenshot)
        th.addWidget(shot)
        self.rec_btn = QPushButton("●  REC")
        self.rec_btn.setObjectName("rec")
        self.rec_btn.setMinimumWidth(110)
        self.rec_btn.clicked.connect(self.toggle_record)
        th.addWidget(self.rec_btn)
        v.addWidget(top)

        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 8)
        body.setSpacing(10)
        self.effects_panel = EffectsPanel(self.engine.effects)
        self.effects_panel.setFixedWidth(300 if self.compact else 340)
        self.effects_panel.selected.connect(self._select_effect)
        self.effects_panel.toggled.connect(self._toggle_effect)
        body.addWidget(self.effects_panel)
        self.preview = PreviewWidget()
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        body.addWidget(self.preview, 1)
        self.side = SettingsPanel(self.engine)
        self.side.setFixedWidth(320 if self.compact else 360)
        body.addWidget(self.side)
        v.addLayout(body, 1)

        s = self.side
        s.params.changed.connect(self._params_changed)
        s.studio.preset_selected.connect(self._apply_preset)
        s.studio.render_changed.connect(self._render_changed)
        s.studio.order_changed.connect(self._params_changed)
        s.camera.restart_requested.connect(self._restart_camera)
        s.record.record_clicked.connect(self.toggle_record)
        s.record.screenshot_clicked.connect(self.screenshot)
        s.record.guide_changed.connect(self._update_guide)
        self._update_guide()

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.sb_gpu = QLabel("GPU: —")
        self.sb_cam = QLabel("Camera: —")
        self.sb_trk = QLabel("Tracking: —")
        self.sb_render = QLabel("Render: —")
        for w in (self.sb_gpu, self.sb_cam, self.sb_trk, self.sb_render):
            sb.addWidget(w)
        hint = QLabel("Shortcuts: R record · P screenshot · ←/→ presets · F next filter · C clear · Tab clean view · F11 fullscreen")
        sb.addPermanentWidget(hint)
        first = next((e for e in self.engine.effects if e.enabled), self.engine.effects[0])
        self._select_effect(first)

    def _shortcuts(self):
        def sc(key, fn):
            QShortcut(QKeySequence(key), self, activated=fn)
        sc("R", self.toggle_record)
        sc("P", self.screenshot)
        sc("Tab", self.toggle_clean)
        sc("F11", self.toggle_fullscreen)
        sc("Escape", self._escape)
        sc("Right", lambda: self._cycle_preset(1))
        sc("Left", lambda: self._cycle_preset(-1))
        sc("F", lambda: self.engine.perform_action("next_filter"))
        sc("C", lambda: self.engine.perform_action("reset_effects"))
        for i in range(min(9, len(PRESET_NAMES))):
            sc(str(i + 1), lambda i=i: self._apply_preset(PRESET_NAMES[i]))

    # ------------------------------------------------------------------ engine lifecycle
    def _start_engine(self):
        try:
            if self.engine.renderer is None:
                self.engine._make_renderer()
            self.sb_gpu.setText(f"GPU: {self.engine.renderer.gpu_name}")
        except Exception as exc:
            log.exception("renderer")
            self._fatal("Graphics problem", str(exc))
            return
        self._launch_live()

    def _launch_live(self):
        if self._starting:
            return
        self._starting = True
        self.preview.message = "Starting camera and hand tracking..."
        self.preview.submessage = "First launch downloads the hand-tracking model (≈8 MB)."
        self.preview.update()

        def work():
            try:
                err = self.engine.start_live()
                if self.engine.tracker:
                    self.engine.tracker.low_light_boost = self.settings.tracking.low_light
            except Exception as exc:  # pragma: no cover
                log.exception("start_live")
                err = str(exc)
            self._bridge.started.emit(err)
        threading.Thread(target=work, daemon=True, name="EngineStart").start()
        self.timer.start(1000 // 60)

    def _on_started(self, err):
        self._starting = False
        if err:
            log.error("start failed: %s", err)
            self.preview.message = "Camera not available"
            self.preview.submessage = err + "\n\nChoose another camera in the Camera tab and press Apply."
            self.preview.update()
            self.side.tabs.setCurrentIndex(3)
        else:
            self.preview.submessage = ""
            self.preview.toast(f"Preset: {self.engine.preset}")

    def _restart_camera(self):
        if self.recorder.recording:
            self.toggle_record()
        self.timer.stop()
        self.engine.stop_live()
        self._launch_live()

    # ------------------------------------------------------------------ main loop
    def _tick(self):
        try:
            img = self.engine.tick()
        except Exception as exc:
            log.exception("tick")
            self.preview.message = "Rendering error"
            self.preview.submessage = str(exc)
            self.preview.update()
            return
        if img is None:
            cam = self.engine.camera
            if cam is not None and cam.error and not self._starting:
                self.preview.message = "Camera disconnected"
                self.preview.submessage = cam.error
                self.preview.update()
            return
        self._last_frame = img
        self.preview.set_frame(img)
        if self.recorder.recording:
            self.recorder.push(img, self._focus_x())
            if self.recorder.error:
                err = self.recorder.error
                self.toggle_record()
                QMessageBox.warning(self, "Recording stopped", err)
        self._frames += 1
        now = time.perf_counter()
        if now - self._fps_t >= 0.5:
            self._fps = self._frames / (now - self._fps_t)
            self._frames = 0
            self._fps_t = now
            self.preview.fps = self._fps

    def _focus_x(self) -> float:
        tr = self.engine.last_tracking
        if tr and tr.hands:
            return float(np.mean([h.palm_uv[0] for h in tr.hands]))
        return self.recorder.focus_x

    def _ui_update(self):
        e = self.engine
        gf = e.last_gestures
        tr = e.last_tracking
        gl = []
        if gf and tr:
            for h in tr.hands:
                g = gf.hands.get(h.hand_id)
                if g and h.presence > 0.5:
                    gl.append((h.label, g.gesture, g.pinch))
        self.preview.gestures = gl
        statuses = [x.status for x in e.active_effects() if x.status and x.id in ("filter_frame",)]
        self.preview.status = statuses[0] if statuses else ""
        self.preview.recording = self.recorder.recording
        self.preview.rec_time = self.recorder.duration
        self.preview.crop_focus = self.recorder._smooth_focus if self.recorder.recording else self._focus_x()
        if self.recorder.recording:
            m, s = divmod(int(self.recorder.duration), 60)
            self.rec_btn.setText(f"■  {m:02d}:{s:02d}")
            self.side.record.rec_info.setText(f"Recording {m:02d}:{s:02d} · {self.recorder.frames_written} frames"
                                              + (f" · {self.recorder.frames_dropped} dropped" if self.recorder.frames_dropped else ""))
        if self.side.tabs.currentIndex() == 0:
            self.side.params.refresh_values()
        elif self.side.tabs.currentIndex() == 3:
            self.side.camera.update_stats()
        elif self.side.tabs.currentIndex() == 4:
            self.side.gestures.update_live()
        cam = e.camera
        if cam:
            self.sb_cam.setText(f"Camera: {cam.width}×{cam.height} @ {cam.measured_fps:.0f} FPS")
        if e.tracker:
            self.sb_trk.setText(f"Tracking: {e.tracker.fps:.0f} FPS · {e.stats['hands']} hand(s)")
        self.sb_render.setText(f"Render: {e.stats['render_ms']:.1f} ms · {self._fps:.0f} FPS")
        # live thumbnails for active effects
        if self._last_frame is not None and tr and tr.hands:
            now = time.perf_counter()
            for eff in e.active_effects():
                if now - self._thumb_time.get(eff.id, 0) > 15 and eff.id in self.effects_panel.cards:
                    self.effects_panel.cards[eff.id].set_live_thumbnail(self._last_frame)
                    self._thumb_time[eff.id] = now
                    break
        if e.preset != self.preset_box.currentText():
            self._sync_preset_ui()

    # ------------------------------------------------------------------ actions
    def _apply_preset(self, name):
        if name not in PRESET_NAMES:
            return
        self.engine.apply_preset(name)
        self._sync_preset_ui()
        self.preview.toast(f"Preset: {name}")

    def _cycle_preset(self, step):
        i = PRESET_NAMES.index(self.engine.preset) if self.engine.preset in PRESET_NAMES else 0
        self._apply_preset(PRESET_NAMES[(i + step) % len(PRESET_NAMES)])

    def _sync_preset_ui(self):
        self.preset_box.blockSignals(True)
        self.preset_box.setCurrentText(self.engine.preset)
        self.preset_box.blockSignals(False)
        self.intensity.set_value(self.settings.render.master_intensity, silent=True)
        self.effects_panel.sync_all()
        self.side.studio.sync()
        sel = self.side.params.effect
        if sel is not None:
            self.side.params.set_effect(sel, self._toggle_effect)
            self.effects_panel.select(sel)

    def _on_action(self, action):
        labels = {"next_preset": f"Preset: {self.engine.preset}", "prev_preset": f"Preset: {self.engine.preset}",
                  "reset_effects": "Cleared particles & trails"}
        if action == "next_filter":
            ff = self.engine.effect("filter_frame")
            self.preview.toast(f"Filter: {ff.mode.name}" if ff else "Next filter")
        elif action == "screenshot":
            self.screenshot()
        elif action == "toggle_record":
            QTimer.singleShot(0, self.toggle_record)
        elif action in labels:
            self.preview.toast(labels[action])

    def _select_effect(self, effect):
        self.side.params.set_effect(effect, self._toggle_effect)
        self.effects_panel.select(effect)
        self.side.tabs.setCurrentIndex(0)

    def _toggle_effect(self, effect, on):
        effect.enabled = on
        if on:
            effect.reset()
        self.effects_panel.sync_all()
        if self.side.params.effect is effect:
            self.side.params.switch.set_silent(on)
        self.side.studio.refresh_layers()

    def _params_changed(self):
        self.side.studio.refresh_layers()

    def _render_changed(self):
        rs = self.settings.render
        r = self.engine.renderer
        if r and r.quality != rs.quality:
            r.quality = rs.quality
            r.width = 0   # force re-allocation at the new quality
            r.resize(self.settings.camera.width, self.settings.camera.height)
            for e in self.engine.effects:
                e.on_resize(r)
        self.engine.apply_render_settings()
        self.intensity.set_value(rs.master_intensity, silent=True)

    def _set_intensity(self, v):
        self.settings.render.master_intensity = v
        self.engine.apply_render_settings()
        self.side.studio.intensity.set_value(v, silent=True)

    def _update_guide(self):
        rs = self.settings.recording
        self.preview.crop_guide = rs.format if self.side.record.guide.isChecked() and rs.format != "16:9" else None

    def toggle_record(self):
        rs = self.settings.recording
        if not self.recorder.recording:
            if self._last_frame is None:
                self.preview.toast("No camera image yet")
                return
            h, w = self._last_frame.shape[:2]
            try:
                path = self.recorder.start(rs.output_dir, rs.format, rs.resolution, rs.fps, rs.quality, (w, h),
                                           self.side.record.smart.isChecked())
            except Exception as exc:
                QMessageBox.warning(self, "Could not start recording", str(exc))
                return
            log.info("recording to %s", path)
            self.rec_btn.setProperty("recording", "true")
            self.side.record.set_recording(True)
            self.preview.toast("Recording started")
        else:
            info = self.recorder.stop()
            self.rec_btn.setProperty("recording", "false")
            self.rec_btn.setText("●  REC")
            self.side.record.set_recording(False)
            self.side.record.rec_info.setText("")
            if info and info.frames > 0:
                thumb = None
                cap = cv2.VideoCapture(info.path)
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, info.frames // 2))
                ok, fr = cap.read()
                cap.release()
                if ok:
                    thumb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
                self.side.record.set_last(info, thumb)
                self.preview.toast(f"Saved {info.duration:.0f}s video → Record tab")
                self.side.tabs.setCurrentIndex(2)
            if self.recorder.error:
                QMessageBox.warning(self, "Recording problem", self.recorder.error)
        self.rec_btn.style().unpolish(self.rec_btn)
        self.rec_btn.style().polish(self.rec_btn)

    def screenshot(self):
        if self._last_frame is None:
            return
        d = os.path.join(self.settings.recording.output_dir, "Screenshots")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"HandFX_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.png")
        cv2.imwrite(path, cv2.cvtColor(self._last_frame, cv2.COLOR_RGB2BGR))
        self.preview.toast("Screenshot saved")
        log.info("screenshot %s", path)

    def toggle_clean(self):
        self._clean = not self._clean
        self.effects_panel.setVisible(not self._clean)
        self.side.setVisible(not self._clean)
        self.preview.hud = not self._clean

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _escape(self):
        if self.isFullScreen():
            self.showNormal()
        elif self._clean:
            self.toggle_clean()

    def _fatal(self, title, msg):
        self.preview.message = title
        self.preview.submessage = msg
        self.preview.update()
        QMessageBox.critical(self, title, msg)

    def closeEvent(self, event):
        try:
            if self.recorder.recording:
                self.recorder.stop()
            self.timer.stop()
            self.engine.save_effect_settings()
        finally:
            self.engine.shutdown()
        super().closeEvent(event)
