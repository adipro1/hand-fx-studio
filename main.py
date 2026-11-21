"""HAND FX STUDIO — real-time hand-tracking visual effects.

Run with start.bat (recommended) or:  python main.py
Options:
    --safe       start with no effects enabled (troubleshooting)
    --reset      reset all settings to defaults
"""
from __future__ import annotations

import logging
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
LOG_PATH = os.path.join(ROOT, "hand_fx_studio.log")


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    os.environ.setdefault("GLOG_minloglevel", "2")       # quieten MediaPipe
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def main() -> int:
    setup_logging()
    log = logging.getLogger("hfx")
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError as exc:
        print("PySide6 is not installed. Please run start.bat to install dependencies.\n", exc)
        return 1

    from core.configuration import SETTINGS_PATH, AppSettings
    from interface.theme import STYLESHEET

    if "--reset" in sys.argv and os.path.exists(SETTINGS_PATH):
        os.remove(SETTINGS_PATH)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("HAND FX STUDIO")
    app.setStyleSheet(STYLESHEET)

    def excepthook(etype, value, tb):
        msg = "".join(traceback.format_exception(etype, value, tb))
        log.error("Unhandled exception:\n%s", msg)
        QMessageBox.critical(None, "HAND FX STUDIO - unexpected error",
                             f"{value}\n\nDetails were written to:\n{LOG_PATH}")
    sys.excepthook = excepthook

    settings = AppSettings.load()
    if "--safe" in sys.argv:
        settings.effects = {}
        settings.active_preset = "Clean Camera"

    from interface.main_window import MainWindow
    win = MainWindow(settings)
    if win.compact:
        win.showMaximized()
    else:
        win.show()
    log.info("HAND FX STUDIO started")
    if "--selftest" in sys.argv:
        # Developer check: launch, run for a few seconds, save a window capture, quit.
        from PySide6.QtCore import QTimer
        i = sys.argv.index("--selftest")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else os.path.join(ROOT, "selftest.png")
        secs = float(sys.argv[i + 2]) if len(sys.argv) > i + 2 else 8.0

        def opt(name):
            return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None
        if opt("--preset"):
            QTimer.singleShot(500, lambda: win._apply_preset(opt("--preset")))
        if opt("--tab"):
            QTimer.singleShot(600, lambda: win.side.tabs.setCurrentIndex(int(opt("--tab"))))

        if "--record" in sys.argv:
            if opt("--format"):
                win.settings.recording.format = opt("--format")
            QTimer.singleShot(4500, win.toggle_record)
            QTimer.singleShot(int(secs * 1000) - 700, win.toggle_record)

        def finish():
            if win.recorder.last_info:
                li = win.recorder.last_info
                log.info("selftest recording: %s %dx%d frames=%d dur=%.1fs dropped=%d err=%s", li.path,
                         li.width, li.height, li.frames, li.duration, li.dropped, win.recorder.error)
            win.grab().save(out)
            log.info("selftest: fps=%.1f render=%.1fms hands=%d capture=%s", win._fps,
                     win.engine.stats["render_ms"], win.engine.stats["hands"], out)
            win.close()
        QTimer.singleShot(int(secs * 1000), finish)
    rc = app.exec()
    log.info("exit %s", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
