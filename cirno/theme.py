"""Estética Komi en Qt: papel y tinta, esquinas 0, bordes gruesos y sombras duras. Paleta Cirno (hielo)."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

PAPER = "#EEF6FB"
INK = "#10233A"
BLUE = "#2E7DE9"
BLUE_DARK = "#1F66C8"
ICE = "#DDEEFB"
ICE_DARK = "#9ED8FF"
MUTED = "#6B7B8F"
DANGER = "#D64545"

QSS = f"""
* {{
    font-family: "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 10.5pt;
    color: {INK};
}}
QMainWindow, QDialog, QMessageBox, QWidget#root {{ background: {PAPER}; }}
QLabel#titulo {{ font-size: 28pt; font-weight: 900; letter-spacing: 3px; }}
QLabel#kana {{ font-size: 16pt; font-weight: 700; color: {BLUE}; }}
QLabel#kicker {{ font-size: 8.5pt; font-weight: 700; letter-spacing: 3px; color: {BLUE}; }}
QLabel#version {{ font-size: 8.5pt; color: {MUTED}; }}
QLabel#seccion {{ font-size: 9pt; font-weight: 800; letter-spacing: 2px; }}
QLabel#nota {{ color: {MUTED}; font-size: 9pt; }}

QFrame#panel {{ background: #FFFFFF; border: 2px solid {INK}; border-radius: 0; }}

QPushButton {{
    background: #FFFFFF; color: {INK};
    border: 2px solid {INK}; border-radius: 0;
    padding: 6px 14px; font-weight: 700;
}}
QPushButton:hover {{ background: {ICE}; }}
QPushButton:pressed {{ background: {ICE_DARK}; }}
QPushButton:disabled {{ color: #8A98A8; border-color: #B8C4D1; background: #F6F9FC; }}
QPushButton#primario {{ background: {BLUE}; color: #FFFFFF; font-size: 12.5pt; padding: 10px 28px; letter-spacing: 2px; }}
QPushButton#primario:hover {{ background: {BLUE_DARK}; }}
QPushButton#primario:pressed {{ background: {INK}; }}
QPushButton#primario:disabled {{ background: #B8C4D1; color: #FFFFFF; border-color: #B8C4D1; }}
QPushButton#texto {{ border: none; background: transparent; text-decoration: underline; padding: 2px 4px; }}
QPushButton#texto:hover {{ color: {BLUE}; }}

QListWidget, QPlainTextEdit, QLineEdit {{
    background: #FFFFFF; border: 2px solid {INK}; border-radius: 0; padding: 4px;
    selection-background-color: {ICE_DARK}; selection-color: {INK};
}}
QListWidget::item {{ padding: 4px 6px; }}
QListWidget::item:selected {{ background: {ICE_DARK}; color: {INK}; }}
QLineEdit:disabled, QPlainTextEdit:disabled {{ color: #8A98A8; background: #F6F9FC; }}
QPlainTextEdit {{ font-family: "Cascadia Mono", "Consolas", monospace; font-size: 9.5pt; }}

QProgressBar {{
    border: 2px solid {INK}; border-radius: 0; background: #FFFFFF;
    text-align: center; font-weight: 700; height: 22px;
}}
QProgressBar::chunk {{ background: {BLUE}; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 2px solid {INK}; border-radius: 0; background: #FFFFFF;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {BLUE}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: #B8C4D1; }}

QScrollBar:vertical {{ background: {ICE}; width: 12px; border: none; }}
QScrollBar::handle:vertical {{ background: {INK}; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {ICE}; height: 12px; border: none; }}
QScrollBar::handle:horizontal {{ background: {INK}; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QToolTip {{ background: {INK}; color: #FFFFFF; border: none; padding: 4px 6px; }}
"""


def sombra(widget: QWidget, desplazamiento: int = 4) -> None:
    """Sombra dura (sin desenfoque) al estilo Komi."""
    efecto = QGraphicsDropShadowEffect(widget)
    efecto.setBlurRadius(0)
    efecto.setOffset(desplazamiento, desplazamiento)
    efecto.setColor(QColor(INK))
    widget.setGraphicsEffect(efecto)
