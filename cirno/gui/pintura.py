"""Pintar las marcas con QPainter, en el espacio base de la página (puntos, Y hacia abajo).
Lo usan las miniaturas de la rejilla y el editor, para que se vea lo mismo en los dos sitios
y lo mismo que luego escribe `marcas_pdf` en el archivo."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF

from ..pdf.marcas import ASCENSO, INTERLINEA, Caja, Imagen, Linea, Texto, Trazo, lineas, punta_flecha

FAMILIAS = {"sans": "Arial", "serif": "Times New Roman", "mono": "Courier New"}
CUERPO_REF = 100  # las letras se pintan a 100 px y se escalan: así valen los cuerpos con decimales

_imagenes: dict[int, QImage] = {}


def color(c: str, opacidad: float = 1.0) -> QColor:
    q = QColor("#" + c.lstrip("#"))
    q.setAlphaF(max(0.0, min(1.0, opacidad)))
    return q


def fuente_qt(m: Texto) -> QFont:
    f = QFont(FAMILIAS.get(m.fuente, "Arial"))
    f.setPixelSize(CUERPO_REF)
    f.setBold(m.negrita)
    f.setItalic(m.cursiva)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def imagen_qt(datos: bytes) -> QImage:
    clave = hash(datos)
    if clave not in _imagenes:
        if len(_imagenes) > 64:
            _imagenes.clear()
        _imagenes[clave] = QImage.fromData(datos)
    return _imagenes[clave]


def pintar_marca(p: QPainter, m) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if isinstance(m, Texto):
        p.translate(m.x, m.y)
        if m.angulo:
            p.rotate(m.angulo)
        escala = m.cuerpo / CUERPO_REF
        p.scale(escala, escala)
        p.setFont(fuente_qt(m))
        p.setPen(color(m.color, m.opacidad))
        for i, (linea, dx) in enumerate(lineas(m)):
            p.drawText(QPointF(dx / escala, (ASCENSO + INTERLINEA * i) * CUERPO_REF), linea)
    elif isinstance(m, Caja):
        r = QRectF(m.x, m.y, m.ancho, m.alto)
        if m.resalte:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        if m.relleno:
            p.fillRect(r, color(m.relleno, m.opacidad))
        if m.borde:
            p.setPen(QPen(color(m.borde, m.opacidad), m.grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
    elif isinstance(m, Linea):
        p.setPen(QPen(color(m.color), m.grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x2, y2 = m.x2, m.y2
        if m.flecha:
            punta = punta_flecha(m)
            x2, y2 = (punta[1][0] + punta[2][0]) / 2, (punta[1][1] + punta[2][1]) / 2
        p.drawLine(QPointF(m.x1, m.y1), QPointF(x2, y2))
        if m.flecha:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color(m.color))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in punta]))
    elif isinstance(m, Trazo):
        if m.puntos:
            p.setPen(QPen(color(m.color), m.grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(camino_trazo(m))
    elif isinstance(m, Imagen):
        im = imagen_qt(m.datos)
        if not im.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setOpacity(m.opacidad)
            if m.angulo:
                p.translate(m.x + m.ancho / 2, m.y + m.alto / 2)
                p.rotate(m.angulo)
                p.translate(-(m.x + m.ancho / 2), -(m.y + m.alto / 2))
            p.drawImage(QRectF(m.x, m.y, m.ancho, m.alto), im)
    p.restore()


def camino_trazo(m: Trazo) -> QPainterPath:
    camino = QPainterPath(QPointF(*m.puntos[0]))
    for x, y in m.puntos[1:] or m.puntos[:1]:
        camino.lineTo(x, y)
    return camino


def pintar_marcas(p: QPainter, marcas) -> None:
    for m in marcas:
        pintar_marca(p, m)
