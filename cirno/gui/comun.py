"""Piezas que comparten las pestañas: recursos, ajustes, imágenes de Pillow a Qt y contraseñas."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtWidgets import QInputDialog, QLineEdit, QWidget

from .. import APP_NAME, ORG


def ruta_recurso(nombre: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    for candidata in (base / "cirno" / "assets" / nombre, base / "assets" / nombre,
                      Path(__file__).resolve().parents[1] / "assets" / nombre):
        if candidata.exists():
            return candidata
    return base / "assets" / nombre


def ajustes() -> QSettings:
    return QSettings(ORG, APP_NAME)


def a_qimage(imagen: Image.Image) -> QImage:
    """Copia la imagen de Pillow a un QImage que no depende de su memoria."""
    if imagen.mode != "RGB":
        imagen = imagen.convert("RGB")
    datos = imagen.tobytes()
    return QImage(datos, imagen.width, imagen.height, imagen.width * 3, QImage.Format.Format_RGB888).copy()


def pedir_clave(padre: QWidget, nombre: str, reintento: bool = False) -> str | None:
    aviso = "La contraseña no es correcta.\n\n" if reintento else ""
    texto, ok = QInputDialog.getText(padre, APP_NAME, f"{aviso}«{nombre}» está protegido. Contraseña:",
                                     QLineEdit.EchoMode.Password)
    return texto if ok and texto else None


def abrir_en_sistema(ruta: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))


def carpeta_inicial(clave: str, defecto: Path | None = None) -> str:
    valor = ajustes().value(clave, "")
    if valor and Path(str(valor)).is_dir():
        return str(valor)
    return str(defecto or Path.home() / "Documents")


def recordar_carpeta(clave: str, ruta: str | Path) -> None:
    p = Path(ruta)
    ajustes().setValue(clave, str(p if p.is_dir() else p.parent))
