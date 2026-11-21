"""Visual theme: dark, minimal, neon accents."""
from __future__ import annotations

BG = "#090b10"
PANEL = "#0f1218"
CARD = "#151922"
CARD_HOVER = "#1b2130"
BORDER = "#222838"
TEXT = "#e8ecf5"
MUTED = "#8891a5"
DIM = "#5b6378"
CYAN = "#22e3ff"
MAGENTA = "#ff3dc8"
VIOLET = "#8b5cff"
RED = "#ff3b5c"
GREEN = "#35f29a"

FONT = "Segoe UI Variable Text, Segoe UI, Inter, Arial"

import os as _os
_ICONS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "assets", "icons").replace("\\", "/")

CATEGORY_COLORS = {
    "Reference FX": ("#ff3dc8", "#22e3ff"),
    "Tracking": ("#35f29a", "#22e3ff"),
    "Distortion": ("#8b5cff", "#22e3ff"),
    "Portals": ("#ff7a18", "#ffd23f"),
    "Colour": ("#ff3dc8", "#ffd23f"),
    "Particles": ("#22e3ff", "#8b5cff"),
    "Energy": ("#4fc3ff", "#ffffff"),
    "Geometry": ("#00f0ff", "#b44bff"),
}

CATEGORY_ORDER = ["Reference FX", "Tracking", "Distortion", "Portals", "Colour",
                  "Particles", "Energy", "Geometry"]

STYLESHEET = f"""
* {{
    font-family: {FONT};
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}
QMainWindow, QWidget#root {{ background: {BG}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#topbar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#dim {{ color: {DIM}; font-size: 11px; }}
QLabel#h1 {{ font-size: 17px; font-weight: 600; }}
QLabel#h2 {{ font-size: 14px; font-weight: 600; }}
QLabel#section {{ color: {DIM}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; padding-top: 10px; }}
QLabel#chip {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px; padding: 2px 8px; color: {MUTED}; font-size: 11px; }}
QLabel#status {{ color: {CYAN}; font-size: 12px; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}

QPushButton {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px; padding: 7px 14px;
}}
QPushButton:hover {{ background: {CARD_HOVER}; border-color: #2f3850; }}
QPushButton:pressed {{ background: #10131a; }}
QPushButton:disabled {{ color: {DIM}; }}
QPushButton#accent {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10c8e8, stop:1 #8b5cff);
    border: none; color: white; font-weight: 600;
}}
QPushButton#accent:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #36d8f5, stop:1 #a07bff); }}
QPushButton#rec {{ background: #2a1118; border: 1px solid #5a1d2c; color: #ff8aa0; font-weight: 600; }}
QPushButton#rec:hover {{ background: #3a1520; }}
QPushButton#rec[recording="true"] {{ background: {RED}; color: white; border-color: {RED}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {MUTED}; }}
QPushButton#ghost:hover {{ color: {TEXT}; background: {CARD}; }}
QPushButton#seg {{ border-radius: 8px; padding: 6px 10px; }}
QPushButton#seg:checked {{ background: #12303a; border-color: {CYAN}; color: {CYAN}; }}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 9px; min-height: 20px;
}}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: #2f3850; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({_ICONS}/chevron.svg); width: 12px; height: 12px; margin-right: 8px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; selection-background-color: #1d3340;
    selection-color: {CYAN}; padding: 4px; border-radius: 8px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CYAN}, stop:1 {VIOLET}); border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {CYAN}; }}

QTabWidget::pane {{ border: none; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 6px; margin-right: 1px; font-size: 12px; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {CYAN}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QListWidget {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: #1d3340; color: {CYAN}; }}
QProgressBar {{ background: {BORDER}; border: none; border-radius: 3px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CYAN}, stop:1 {MAGENTA}); border-radius: 3px; }}
QStatusBar {{ background: {PANEL}; color: {DIM}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {DIM}; font-size: 11px; padding: 0 8px; }}
QMessageBox {{ background: {PANEL}; }}
"""
