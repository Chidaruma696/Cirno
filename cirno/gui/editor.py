"""El editor de una página: escribir encima, reescribir un texto que ya está (se tapa y se
vuelve a escribir), resaltar, tapar, enmarcar, líneas y flechas, dibujar a mano, pegar
imágenes (sellos, firmas) y recortar. Todo queda como marcas de la página (`pdf/marcas.py`);
el PDF original no se toca hasta guardar, y lo hecho aquí se deshace desde la rejilla."""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pdfplumber
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QFontMetricsF, QImage, QKeySequence, QPainter, QPainterPath, QPainterPathStroker,
    QPen, QPixmap, QPolygonF, QTextCursor, QTransform,
)
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel, QMessageBox, QPushButton, QToolBar, QToolButton, QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..extraccion.tablas import _renglones
from ..pdf import render
from ..pdf.documento import Documento, Pagina
from ..pdf.marcas import (
    AMARILLO, ASCENSO, Caja, Imagen, Linea, Texto, Trazo, _girar, caja_de, esquinas, mover, tamano_texto,
)
from .comun import a_qimage, carpeta_inicial, recordar_carpeta
from .pintura import CUERPO_REF, color, fuente_qt, imagen_qt, pintar_marca

logging.getLogger("pdfminer").setLevel(logging.ERROR)

PPP_EDITOR = 150.0
FILTRO_IMAGEN = "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"

# nombre, etiqueta, atajo, ayuda
HERRAMIENTAS = (
    ("seleccionar", "Seleccionar", "V", "Pulsa una marca para moverla; arrastra su esquina para cambiarle el tamaño; doble clic en un texto para corregirlo. Supr la borra."),
    ("texto", "Texto", "T", "Pulsa donde quieras escribir. Ctrl+Intro o pulsar fuera termina; Esc cancela."),
    ("editar", "Corregir texto", "E", "Pulsa sobre un texto de la página: Cirno lo tapa con el color del fondo y te deja reescribirlo encima."),
    ("resaltar", "Resaltar", "R", "Arrastra sobre el texto: el resaltado se ajusta solo a los renglones."),
    ("tapar", "Tapar", "B", "Arrastra un rectángulo: se rellena con el color del fondo que haya debajo."),
    ("marco", "Marco", "M", "Arrastra para dibujar un recuadro."),
    ("linea", "Línea", "L", "Arrastra para trazar una línea (Mayús la deja recta)."),
    ("flecha", "Flecha", "F", "Arrastra desde el origen hasta donde apunta la flecha."),
    ("dibujar", "Dibujar", "D", "Dibuja a mano alzada: una firma, una rúbrica, un tachón."),
    ("imagen", "Imagen…", "I", "Elige una imagen (un sello, una firma escaneada); luego muévela y cámbiale el tamaño."),
    ("recortar", "Recortar", "X", "Arrastra la parte de la hoja que quieres conservar."),
)
COLORES = {"texto": "000000", "marco": "D32F2F", "linea": "D32F2F", "flecha": "D32F2F", "dibujar": "1A237E", "resaltar": AMARILLO}


def _hex(q: QColor) -> str:
    return f"{q.red():02X}{q.green():02X}{q.blue():02X}"


def _familia(nombre: str) -> tuple[str, bool, bool]:
    """(familia, negrita, cursiva) que más se parece a una fuente del PDF, por su nombre."""
    n = nombre.lower()
    if any(k in n for k in ("courier", "mono", "consol", "typewriter")):
        familia = "mono"
    elif "sans" not in n and any(k in n for k in ("times", "serif", "georgia", "garamond", "cambria", "roman", "book", "minion", "palatino")):
        familia = "serif"
    else:
        familia = "sans"
    return familia, any(k in n for k in ("bold", "black", "heavy", "semibold", "demi")), any(k in n for k in ("italic", "oblique"))


def palabras_de(pagina: Pagina) -> list[dict] | None:
    """Las palabras de la página con su sitio en el espacio base, o None si no se pueden situar
    (la página viene girada en el archivo, o no se puede leer)."""
    try:
        with pdfplumber.open(str(pagina.fuente.ruta), password=pagina.fuente.clave or None) as pdf:
            page = pdf.pages[pagina.indice]
            if page.rotation % 360:
                return None
            dx, dy = page.cropbox[0] - page.bbox[0], page.cropbox[1] - page.bbox[1]
            palabras = page.extract_words(extra_attrs=["fontname", "size"])
    except Exception:  # noqa: BLE001
        return None
    for w in palabras:
        w["x0"], w["x1"], w["top"], w["bottom"] = w["x0"] - dx, w["x1"] - dx, w["top"] - dy, w["bottom"] - dy
    return palabras


class ItemMarca(QGraphicsItem):
    """Una marca en la escena. Se pinta con el mismo código que las miniaturas."""

    def __init__(self, marca, lienzo: "Lienzo") -> None:
        super().__init__()
        self.marca = marca
        self.lienzo = lienzo
        self._redimensiona = False
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def _px(self) -> float:
        """Cuántos puntos de página mide un píxel de pantalla, para que las asas no cambien con el zoom."""
        return 1.0 / max(self.lienzo.transform().m11() ** 2 + self.lienzo.transform().m12() ** 2, 1e-9) ** 0.5

    def fijar(self, marca) -> None:
        self.prepareGeometryChange()
        self.marca = marca
        self.update()

    def redimensionable(self) -> bool:
        return isinstance(self.marca, Caja) or (isinstance(self.marca, Imagen) and self.marca.angulo % 360 == 0)

    def _asa(self) -> QRectF:
        m, t = self.marca, 9.0 * self._px()
        return QRectF(m.x + m.ancho - t / 2, m.y + m.alto - t / 2, t, t)

    def boundingRect(self) -> QRectF:  # noqa: N802
        x, y, ancho, alto = caja_de(self.marca)
        margen = 8.0 * self._px() + 2.0
        return QRectF(x - margen, y - margen, ancho + 2 * margen, alto + 2 * margen)

    def shape(self) -> QPainterPath:
        m = self.marca
        if isinstance(m, (Linea, Trazo)):
            camino = QPainterPath(QPointF(m.x1, m.y1)) if isinstance(m, Linea) else QPainterPath(QPointF(*m.puntos[0]))
            if isinstance(m, Linea):
                camino.lineTo(m.x2, m.y2)
            else:
                for x, y in m.puntos[1:] or m.puntos[:1]:
                    camino.lineTo(x, y)
            trazador = QPainterPathStroker()
            trazador.setWidth(max(m.grosor, 10.0 * self._px()))
            return trazador.createStroke(camino)
        camino = QPainterPath()
        camino.addPolygon(QPolygonF([QPointF(x, y) for x, y in esquinas(m)]))
        camino.closeSubpath()
        if self.isSelected() and self.redimensionable():
            camino.addRect(self._asa())
        return camino

    def paint(self, p: QPainter, _opcion, _widget=None) -> None:
        pintar_marca(p, self.marca)
        if self.isSelected():
            p.setPen(QPen(QColor("#1E88E5"), 0, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in esquinas(self.marca)]))
            if self.redimensionable():
                p.setPen(QPen(QColor("#1E88E5"), 0))
                p.setBrush(QColor("white"))
                p.drawRect(self._asa())

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self.isSelected() and self.redimensionable() and self._asa().contains(e.pos()):
            self._redimensiona = True
            self.lienzo.antes()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._redimensiona:
            m = self.marca
            ancho = max(4.0, e.pos().x() - m.x)
            alto = max(4.0, e.pos().y() - m.y)
            if isinstance(m, Imagen) or e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                alto = ancho * m.alto / max(m.ancho, 0.01)
            self.fijar(replace(m, ancho=ancho, alto=alto))
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._redimensiona:
            self._redimensiona = False
            self.lienzo.cambiado.emit()
            return
        super().mouseReleaseEvent(e)
        self.lienzo.asentar_movimientos()

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        if isinstance(self.marca, Texto):
            self.lienzo.corregir(self)
        else:
            super().mouseDoubleClickEvent(e)


class EdicionTexto(QGraphicsTextItem):
    """El texto mientras se escribe. Al terminar se convierte en una marca `Texto`."""

    def __init__(self, lienzo: "Lienzo", base: Texto, original: Texto | None, previo) -> None:
        super().__init__()
        self.lienzo, self.base, self.original, self.previo = lienzo, base, original, previo
        self.cerrado = False
        letra = fuente_qt(base)
        self.setFont(letra)
        self.setDefaultTextColor(color(base.color))
        self.document().setDocumentMargin(0)
        self.setPlainText(base.texto)
        # La marca pone la línea base a ASCENSO cuerpos del ancla; aquí la letra se sube o baja lo justo para coincidir.
        self.setTransform(QTransform().translate(0, ASCENSO * CUERPO_REF - QFontMetricsF(letra).ascent()))
        self.setScale(base.cuerpo / CUERPO_REF)
        self.setRotation(base.angulo)
        self.setPos(base.x, base.y)
        self.setZValue(1000)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)

    def paint(self, p: QPainter, opcion, widget=None) -> None:
        p.setPen(QPen(QColor("#1E88E5"), 0, Qt.PenStyle.DotLine))
        p.drawRect(self.boundingRect())
        super().paint(p, opcion, widget)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.lienzo.terminar_texto(self, cancelar=True)
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.lienzo.terminar_texto(self)
        else:
            super().keyPressEvent(e)

    def focusOutEvent(self, e) -> None:  # noqa: N802
        super().focusOutEvent(e)
        self.lienzo.terminar_texto(self)


class Sombra(QGraphicsItem):
    """Oscurece lo que el recorte deja fuera."""

    def __init__(self, lienzo: "Lienzo") -> None:
        super().__init__()
        self.lienzo = lienzo
        self.setZValue(900)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(0, 0, self.lienzo.ancho, self.lienzo.alto)

    def paint(self, p: QPainter, _o, _w=None) -> None:
        rc = self.lienzo.recorte
        if not rc:
            return
        fuera = QPainterPath()
        fuera.addRect(self.boundingRect())
        dentro = QPainterPath()
        dentro.addRect(QRectF(*rc))
        p.fillPath(fuera.subtracted(dentro), QColor(0, 0, 0, 120))
        p.setPen(QPen(QColor("#FFB300"), 0, Qt.PenStyle.DashLine))
        p.drawRect(QRectF(*rc))


class Lienzo(QGraphicsView):
    cambiado = Signal()
    pedir_herramienta = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor("#5A5F66"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.herramienta = "seleccionar"
        self.props = {"cuerpo": 12.0, "grosor": 1.5, "fuente": "sans", "negrita": False, "cursiva": False}
        self.colores = dict(COLORES)
        self.pagina: Pagina | None = None
        self.imagen = QImage()
        self.ancho = self.alto = 1.0
        self.giro = 0
        self.recorte = None
        self.palabras: list[dict] | None = None
        self._palabras_leidas = False
        self._pila: list = []
        self._futuro: list = []
        self._inicio: QPointF | None = None
        self._previa: ItemMarca | None = None
        self._puntos: list[tuple[float, float]] = []
        self._edicion: EdicionTexto | None = None
        self._sombra: Sombra | None = None
        self.portapapeles: list = []

    # ------------------------------------------------------------------ página
    def cargar(self, pagina: Pagina, marcas: tuple, recorte) -> None:
        self.terminar_texto()
        self.scene().clear()
        self._edicion = self._previa = None
        self.pagina = pagina
        self.ancho, self.alto = pagina.tamano_base
        self.giro = pagina.rotacion
        self.recorte = recorte
        self.palabras, self._palabras_leidas = None, False
        self._pila, self._futuro = [], []
        try:
            self.imagen = a_qimage(render.pintar(pagina.fuente, pagina.indice, ppp=PPP_EDITOR))
        except Exception:  # noqa: BLE001 - una página que no se pinta se edita sobre blanco
            self.imagen = QImage(int(self.ancho), int(self.alto), QImage.Format.Format_RGB888)
            self.imagen.fill(QColor("white"))
        hoja = QGraphicsPixmapItem(QPixmap.fromImage(self.imagen))
        hoja.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        hoja.setTransform(QTransform.fromScale(self.ancho / self.imagen.width(), self.alto / self.imagen.height()))
        hoja.setZValue(-10)
        self.scene().addItem(hoja)
        self._sombra = Sombra(self)
        self.scene().addItem(self._sombra)
        for m in marcas:
            self.scene().addItem(ItemMarca(m, self))
        margen = 30.0
        self.scene().setSceneRect(-margen, -margen, self.ancho + 2 * margen, self.alto + 2 * margen)
        self.ajustar()
        self.fijar_herramienta(self.herramienta)

    def ajustar(self) -> None:
        self.resetTransform()
        self.rotate(self.giro)
        self.fitInView(QRectF(0, 0, self.ancho, self.alto), Qt.AspectRatioMode.KeepAspectRatio)
        self.scale(0.96, 0.96)

    def acercar(self, factor: float) -> None:
        actual = (self.transform().m11() ** 2 + self.transform().m12() ** 2) ** 0.5
        if 0.08 < actual * factor < 16:
            self.scale(factor, factor)

    def wheelEvent(self, e) -> None:  # noqa: N802
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.acercar(1.2 if e.angleDelta().y() > 0 else 1 / 1.2)
        else:
            super().wheelEvent(e)

    # ------------------------------------------------------------------ estado y deshacer
    def items_marca(self) -> list[ItemMarca]:
        orden = self.scene().items(Qt.SortOrder.AscendingOrder)
        return [it for it in orden if isinstance(it, ItemMarca) and it is not self._previa]

    def marcas(self) -> tuple:
        return tuple(it.marca for it in self.items_marca())

    def estado(self):
        return self.marcas(), self.recorte

    def antes(self, estado=None) -> None:
        """Guarda cómo estaba la página, justo antes de cambiarla."""
        self._pila.append(estado if estado is not None else self.estado())
        del self._pila[:-200]
        self._futuro.clear()

    def _fijar(self, estado) -> None:
        self.terminar_texto()
        for it in self.items_marca():
            self.scene().removeItem(it)
        marcas, self.recorte = estado
        for m in marcas:
            self.scene().addItem(ItemMarca(m, self))
        self.fijar_herramienta(self.herramienta)
        self.scene().update()
        self.cambiado.emit()

    def deshacer(self) -> None:
        self.terminar_texto()
        if self._pila:
            self._futuro.append(self.estado())
            self._fijar(self._pila.pop())

    def rehacer(self) -> None:
        if self._futuro:
            self._pila.append(self.estado())
            self._fijar(self._futuro.pop())

    @property
    def tocada(self) -> bool:
        return bool(self._pila)

    def agregar(self, marca, elegir: bool = False) -> ItemMarca:
        it = ItemMarca(marca, self)
        self.scene().addItem(it)
        self._permisos(it)
        if elegir:
            self.scene().clearSelection()
            it.setSelected(True)
        self.cambiado.emit()
        return it

    def asentar_movimientos(self) -> None:
        """Tras arrastrar: el desplazamiento de cada item pasa a las coordenadas de su marca."""
        movidos = [it for it in self.items_marca() if not it.pos().isNull()]
        if not movidos:
            return
        self.antes()
        for it in movidos:
            d = it.pos()
            it.setPos(0, 0)
            it.fijar(mover(it.marca, d.x(), d.y()))
        self.cambiado.emit()

    def elegidos(self) -> list[ItemMarca]:
        return [it for it in self.items_marca() if it.isSelected()]

    def borrar(self) -> None:
        elegidos = self.elegidos()
        if elegidos:
            self.antes()
            for it in elegidos:
                self.scene().removeItem(it)
            self.cambiado.emit()

    def copiar(self) -> None:
        self.portapapeles = [it.marca for it in self.elegidos()]

    def pegar(self) -> None:
        if not self.portapapeles:
            return
        self.antes()
        self.scene().clearSelection()
        self.portapapeles = [mover(m, 12, 12) for m in self.portapapeles]
        for m in self.portapapeles:
            self.agregar(m).setSelected(True)
        self.pedir_herramienta.emit("seleccionar")

    def cambiar_elegidos(self, **cambios) -> None:
        """Aplica propiedades (color, cuerpo, grosor, fuente…) a las marcas seleccionadas que las tengan."""
        elegidos = self.elegidos()
        hechos = False
        for it in elegidos:
            m = it.marca
            nuevos = {}
            for clave, valor in cambios.items():
                if clave == "color":
                    if isinstance(m, Caja):
                        nuevos["relleno" if m.relleno else "borde"] = valor
                    elif isinstance(m, (Texto, Linea, Trazo)):
                        nuevos["color"] = valor
                elif clave == "grosor" and isinstance(m, (Linea, Trazo, Caja)):
                    nuevos["grosor"] = valor
                elif clave in ("cuerpo", "fuente", "negrita", "cursiva") and isinstance(m, Texto):
                    nuevos[clave] = valor
            if nuevos and replace(m, **nuevos) != m:
                if not hechos:
                    self.antes()
                    hechos = True
                it.fijar(replace(m, **nuevos))
        if hechos:
            self.cambiado.emit()

    # ------------------------------------------------------------------ herramientas
    def _permisos(self, it: ItemMarca) -> None:
        libre = self.herramienta == "seleccionar"
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, libre)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, libre)
        it.setAcceptedMouseButtons(Qt.MouseButton.AllButtons if libre else Qt.MouseButton.NoButton)

    def fijar_herramienta(self, nombre: str) -> None:
        self.terminar_texto()
        self.herramienta = nombre
        libre = nombre == "seleccionar"
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag if libre else QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor if libre else
                                  Qt.CursorShape.IBeamCursor if nombre in ("texto", "editar") else Qt.CursorShape.CrossCursor)
        if not libre:
            self.scene().clearSelection()
        for it in self.items_marca():
            self._permisos(it)

    def _leer_palabras(self) -> list[dict] | None:
        if not self._palabras_leidas:
            self._palabras_leidas = True
            self.palabras = palabras_de(self.pagina)
        return self.palabras

    def color_actual(self) -> str:
        return self.colores.get(self.herramienta, "000000")

    def _muestra(self, x: float, y: float) -> tuple[int, int, int] | None:
        px, py = int(x * self.imagen.width() / self.ancho), int(y * self.imagen.height() / self.alto)
        if 0 <= px < self.imagen.width() and 0 <= py < self.imagen.height():
            q = self.imagen.pixelColor(px, py)
            return q.red(), q.green(), q.blue()
        return None

    def color_de_fondo(self, x: float, y: float, ancho: float, alto: float) -> str:
        """El color que más se repite justo alrededor del rectángulo: con eso se tapa sin que se note."""
        cuenta: Counter = Counter()
        for i in range(13):
            t = i / 12.0
            for px, py in ((x + ancho * t, y - 1.5), (x + ancho * t, y + alto + 1.5), (x - 1.5, y + alto * t), (x + ancho + 1.5, y + alto * t)):
                c = self._muestra(px, py)
                if c:
                    cuenta[(c[0] // 6, c[1] // 6, c[2] // 6)] += 1
        if not cuenta:
            return "FFFFFF"
        r, g, b = (min(v * 6 + 3, 255) for v in cuenta.most_common(1)[0][0])
        return "FFFFFF" if min(r, g, b) >= 250 else f"{r:02X}{g:02X}{b:02X}"

    def color_de_tinta(self, x: float, y: float, ancho: float, alto: float, fondo: str) -> str:
        """El color de dentro del rectángulo que más se aleja del fondo: el de la letra."""
        fr, fg, fb = int(fondo[0:2], 16), int(fondo[2:4], 16), int(fondo[4:6], 16)
        mejor, lejos = (0, 0, 0), -1
        for i in range(25):
            for j in range(7):
                c = self._muestra(x + ancho * (i + 0.5) / 25, y + alto * (j + 0.5) / 7)
                if c:
                    d = abs(c[0] - fr) + abs(c[1] - fg) + abs(c[2] - fb)
                    if d > lejos:
                        mejor, lejos = c, d
        return "{:02X}{:02X}{:02X}".format(*mejor) if lejos >= 90 else "000000"

    def _marca_de_arrastre(self, a: QPointF, b: QPointF, recta: bool = False):
        x, y = min(a.x(), b.x()), min(a.y(), b.y())
        ancho, alto = abs(a.x() - b.x()), abs(a.y() - b.y())
        h = self.herramienta
        if h == "resaltar":
            return Caja(x, y, ancho, alto, relleno=self.color_actual(), resalte=True)
        if h == "tapar":
            return Caja(x, y, ancho, alto, relleno=self.color_de_fondo(x, y, ancho, alto))
        if h == "marco":
            return Caja(x, y, ancho, alto, borde=self.color_actual(), grosor=self.props["grosor"])
        if h == "recortar":
            return Caja(x, y, ancho, alto, borde="FFB300", grosor=1.0)
        if h in ("linea", "flecha"):
            bx, by = b.x(), b.y()
            if recta:  # a múltiplos de 45°
                angulo = round(math.atan2(by - a.y(), bx - a.x()) / (math.pi / 4)) * (math.pi / 4)
                largo = math.hypot(bx - a.x(), by - a.y())
                bx, by = a.x() + largo * math.cos(angulo), a.y() + largo * math.sin(angulo)
            return Linea(a.x(), a.y(), bx, by, color=self.color_actual(), grosor=self.props["grosor"], flecha=h == "flecha")
        if h == "dibujar":
            return Trazo(tuple(self._puntos), color=self.color_actual(), grosor=self.props["grosor"])
        return None

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self.herramienta == "seleccionar" or e.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
            return
        if self._edicion is not None:
            self.terminar_texto()
            return
        self._inicio = self.mapToScene(e.position().toPoint())
        self._puntos = [(self._inicio.x(), self._inicio.y())]

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self.herramienta == "seleccionar" or self._inicio is None:
            super().mouseMoveEvent(e)
            return
        p = self.mapToScene(e.position().toPoint())
        if self.herramienta == "dibujar":
            ux, uy = self._puntos[-1]
            if math.hypot(p.x() - ux, p.y() - uy) >= 0.8:
                self._puntos.append((p.x(), p.y()))
        marca = self._marca_de_arrastre(self._inicio, p, bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        if marca is None:
            return
        if self._previa is None:
            self._previa = ItemMarca(marca, self)
            self._previa.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._previa.setZValue(950)
            self.scene().addItem(self._previa)
        else:
            self._previa.fijar(marca)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self.herramienta == "seleccionar" or self._inicio is None:
            super().mouseReleaseEvent(e)
            return
        inicio, self._inicio = self._inicio, None
        fin = self.mapToScene(e.position().toPoint())
        if self._previa is not None:
            self.scene().removeItem(self._previa)
            self._previa = None
        arrastre = math.hypot(fin.x() - inicio.x(), fin.y() - inicio.y())
        h = self.herramienta
        if h == "texto":
            self.escribir(inicio)
        elif h == "editar":
            self.reescribir(inicio)
        elif h == "dibujar":
            if len(self._puntos) >= 2:
                self.antes()
                self.agregar(Trazo(tuple(self._puntos), color=self.color_actual(), grosor=self.props["grosor"]))
        elif arrastre >= 3.0:
            marca = self._marca_de_arrastre(inicio, fin, bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            if h == "recortar":
                x0, y0 = max(0.0, marca.x), max(0.0, marca.y)
                x1, y1 = min(self.ancho, marca.x + marca.ancho), min(self.alto, marca.y + marca.alto)
                if x1 - x0 >= 18 and y1 - y0 >= 18:
                    self.antes()
                    self.recorte = (x0, y0, x1 - x0, y1 - y0)
                    self.scene().update()
                    self.cambiado.emit()
            elif h == "resaltar":
                self.antes()
                for caja in self._resaltes(marca):
                    self.agregar(caja)
            elif marca is not None:
                self.antes()
                self.agregar(marca)

    def _resaltes(self, caja: Caja) -> list[Caja]:
        """El resaltado, ajustado a los renglones de texto que toca; si no toca ninguno, tal cual."""
        palabras = self._leer_palabras()
        if not palabras:
            return [caja]
        x0, y0, x1, y1 = caja.x, caja.y, caja.x + caja.ancho, caja.y + caja.alto
        salida = []
        for r in _renglones(palabras):
            centro = (r.top + r.bottom) / 2
            if not y0 <= centro <= y1:
                continue
            dentro = [w for w in r.palabras if w["x1"] > x0 and w["x0"] < x1]
            if dentro:
                a, b = min(w["x0"] for w in dentro), max(w["x1"] for w in dentro)
                salida.append(replace(caja, x=a - 1, y=r.top - 1, ancho=b - a + 2, alto=r.bottom - r.top + 2))
        return salida or [caja]

    # ------------------------------------------------------------------ texto
    def escribir(self, donde: QPointF) -> None:
        base = Texto(donde.x(), donde.y() - ASCENSO * self.props["cuerpo"], "", cuerpo=self.props["cuerpo"],
                     color=self.colores["texto"], fuente=self.props["fuente"], negrita=self.props["negrita"],
                     cursiva=self.props["cursiva"], angulo=-float(self.giro))
        if self.giro:  # el clic marca la línea base también cuando la hoja se ve girada
            ax, ay = _girar(donde.x(), donde.y() - ASCENSO * base.cuerpo, donde.x(), donde.y(), -self.giro)
            base = replace(base, x=ax, y=ay)
        self._abrir_edicion(base, None, self.estado())

    def corregir(self, item: ItemMarca) -> None:
        """Vuelve a abrir un texto ya puesto."""
        previo = self.estado()
        m: Texto = item.marca
        if m.alineacion != "izq":  # se edita desde su borde izquierdo
            x0, _, _ = tamano_texto(m)
            ax, ay = _girar(m.x + x0, m.y, m.x, m.y, m.angulo)
            m = replace(m, x=ax, y=ay, alineacion="izq")
        self.scene().removeItem(item)
        self._abrir_edicion(m, item.marca, previo)

    def reescribir(self, donde: QPointF) -> None:
        """Tapa el trozo de texto que hay bajo el clic y lo abre para escribirlo de nuevo."""
        palabras = self._leer_palabras()
        if palabras is None:
            QMessageBox.information(self, APP_NAME, "En esta página no puedo localizar el texto (viene girada o es un escaneo).\n\n"
                                    "Usa «Tapar» y luego «Texto».")
            return
        x, y = donde.x(), donde.y()
        for r in _renglones(palabras):
            if not r.top - 2 <= y <= r.bottom + 2:
                continue
            for a, b in r.trozos:
                if a - 2 <= x <= b + 2:
                    trozo = [w for w in r.palabras if w["x0"] >= a - 0.5 and w["x1"] <= b + 0.5]
                    if trozo:
                        self._tapar_y_abrir(trozo)
                        return
        QMessageBox.information(self, APP_NAME, "Ahí no hay texto. Pulsa justo encima de las letras que quieras corregir.")

    def _tapar_y_abrir(self, trozo: list[dict]) -> None:
        x0, x1 = min(w["x0"] for w in trozo), max(w["x1"] for w in trozo)
        top, bottom = min(w["top"] for w in trozo), max(w["bottom"] for w in trozo)
        cuerpo = sorted(float(w.get("size") or (w["bottom"] - w["top"])) for w in trozo)[len(trozo) // 2]
        familia, negrita, cursiva = _familia(str(trozo[0].get("fontname") or ""))
        fondo = self.color_de_fondo(x0 - 1, top - 1, x1 - x0 + 2, bottom - top + 2)
        tinta = self.color_de_tinta(x0, top, x1 - x0, bottom - top, fondo)
        previo = self.estado()
        self.agregar(Caja(x0 - 1, top - 1, x1 - x0 + 2, bottom - top + 2, relleno=fondo))
        base = Texto(x0, bottom - cuerpo * 1.01, " ".join(w["text"] for w in trozo), cuerpo=round(cuerpo, 2), color=tinta,
                     fuente=familia, negrita=negrita, cursiva=cursiva)
        self._abrir_edicion(base, None, previo, conservar_si_igual=True)

    def _abrir_edicion(self, base: Texto, original: Texto | None, previo, conservar_si_igual: bool = False) -> None:
        self.terminar_texto()
        ed = EdicionTexto(self, base, original, previo)
        ed.conservar = conservar_si_igual
        self.scene().addItem(ed)
        self._edicion = ed
        ed.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = ed.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        ed.setTextCursor(cursor)

    def terminar_texto(self, ed: EdicionTexto | None = None, cancelar: bool = False) -> None:
        ed = ed or self._edicion
        if ed is None or ed.cerrado:
            return
        ed.cerrado = True
        self._edicion = None
        texto = "\n".join(linea.rstrip() for linea in ed.toPlainText().split("\n")).strip("\n")
        if ed.scene() is not None:
            self.scene().removeItem(ed)
        tapado = getattr(ed, "conservar", False)  # venía de «Corregir texto»: ya hay una caja tapando el original
        if cancelar:
            if ed.original is not None:
                self.agregar(ed.original)
            elif tapado:  # no se reescribió: se quita también la caja
                self._fijar(ed.previo)
            return
        if ed.original is not None and texto == ed.original.texto:
            self.agregar(ed.original)  # se abrió y se dejó igual
            return
        if texto.strip():
            self.agregar(replace(ed.base, texto=texto))
        elif ed.original is None and not tapado:
            return  # un texto nuevo que se quedó vacío: no ha pasado nada
        self.antes(ed.previo)
        self.cambiado.emit()

    # ------------------------------------------------------------------ imagen
    def poner_imagen(self, datos: bytes) -> bool:
        im = imagen_qt(datos)
        if im.isNull():
            return False
        ancho = min(self.ancho * 0.35, 220.0)
        alto = ancho * im.height() / max(im.width(), 1)
        centro = self.mapToScene(self.viewport().rect().center())
        cx = min(max(centro.x(), ancho / 2), self.ancho - ancho / 2)
        cy = min(max(centro.y(), alto / 2), self.alto - alto / 2)
        self.antes()
        self.pedir_herramienta.emit("seleccionar")
        self.agregar(Imagen(cx - ancho / 2, cy - alto / 2, ancho, alto, datos, angulo=-float(self.giro)), elegir=True)
        return True

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if self._edicion is None and e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.borrar()
        else:
            super().keyPressEvent(e)


class EditorPagina(QDialog):
    """La ventana del editor. `cambios()` devuelve las páginas que quedaron distintas."""

    def __init__(self, padre: QWidget, documento: Documento, fila: int) -> None:
        super().__init__(padre)
        self.documento = documento
        self.fila = fila
        self.trabajo: dict[int, tuple] = {}  # fila → (marcas, recorte) de las hojas ya tocadas
        self.setWindowTitle("Editar hoja")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.lienzo = Lienzo()
        self.lienzo.cambiado.connect(self._refrescar)
        self.lienzo.pedir_herramienta.connect(self._elegir)
        self.lienzo.scene().selectionChanged.connect(self._seleccion)
        self._construir()
        pantalla = (padre.screen() if padre else self.screen()).availableGeometry()
        self.resize(min(1180, int(pantalla.width() * 0.9)), min(900, int(pantalla.height() * 0.9)))
        self._cargar(fila)

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        QTimer.singleShot(0, self.lienzo.ajustar)  # con la ventana ya a su tamaño, la hoja entera a la vista

    # ------------------------------------------------------------------ construcción
    def _construir(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(6)

        barra = QToolBar()
        barra.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.grupo = QActionGroup(self)
        self.acciones: dict[str, QAction] = {}
        for nombre, etiqueta, atajo, ayuda in HERRAMIENTAS:
            a = QAction(etiqueta, self, checkable=True)
            a.setShortcut(QKeySequence(atajo))
            a.setToolTip(f"{ayuda} ({atajo})")
            a.triggered.connect(lambda _=False, n=nombre: self._elegir(n))
            self.grupo.addAction(a)
            barra.addAction(a)
            self.acciones[nombre] = a
        col.addWidget(barra)

        fila = QHBoxLayout()
        self.btn_color = QPushButton("Color")
        self.btn_color.clicked.connect(self._color)
        fila.addWidget(self.btn_color)
        fila.addWidget(QLabel("Letra:"))
        self.fuente = QComboBox()
        for clave, nombre in (("sans", "Sin remates (Arial)"), ("serif", "Con remates (Times)"), ("mono", "Máquina (Courier)")):
            self.fuente.addItem(nombre, clave)
        self.fuente.currentIndexChanged.connect(lambda: self._prop("fuente", self.fuente.currentData()))
        fila.addWidget(self.fuente)
        self.cuerpo = QDoubleSpinBox()
        self.cuerpo.setRange(4, 300)
        self.cuerpo.setDecimals(1)
        self.cuerpo.setValue(12)
        self.cuerpo.setSuffix(" pt")
        self.cuerpo.valueChanged.connect(lambda v: self._prop("cuerpo", float(v)))
        fila.addWidget(self.cuerpo)
        self.negrita = QToolButton()
        self.negrita.setText("N")
        self.negrita.setCheckable(True)
        self.negrita.setToolTip("Negrita")
        self.negrita.toggled.connect(lambda si: self._prop("negrita", si))
        self.cursiva = QToolButton()
        self.cursiva.setText("K")
        self.cursiva.setCheckable(True)
        self.cursiva.setToolTip("Cursiva")
        self.cursiva.toggled.connect(lambda si: self._prop("cursiva", si))
        fila.addWidget(self.negrita)
        fila.addWidget(self.cursiva)
        fila.addSpacing(12)
        fila.addWidget(QLabel("Grosor:"))
        self.grosor = QDoubleSpinBox()
        self.grosor.setRange(0.3, 30)
        self.grosor.setDecimals(1)
        self.grosor.setSingleStep(0.5)
        self.grosor.setValue(1.5)
        self.grosor.setSuffix(" pt")
        self.grosor.valueChanged.connect(lambda v: self._prop("grosor", float(v)))
        fila.addWidget(self.grosor)
        fila.addStretch()
        for texto, funcion, ayuda in (("Deshacer", self.lienzo.deshacer, "Ctrl+Z"), ("Rehacer", self.lienzo.rehacer, "Ctrl+Y")):
            b = QPushButton(texto)
            b.setToolTip(ayuda)
            b.clicked.connect(funcion)
            fila.addWidget(b)
            setattr(self, "btn_" + texto.lower(), b)
        col.addLayout(fila)

        self.pista = QLabel("")
        self.pista.setWordWrap(True)
        col.addWidget(self.pista)
        col.addWidget(self.lienzo, 1)

        pie = QHBoxLayout()
        self.btn_antes = QPushButton("◀")
        self.btn_antes.setToolTip("Hoja anterior (Re Pág)")
        self.btn_antes.clicked.connect(lambda: self._ir(self.fila - 1))
        self.etiqueta = QLabel("")
        self.btn_despues = QPushButton("▶")
        self.btn_despues.setToolTip("Hoja siguiente (Av Pág)")
        self.btn_despues.clicked.connect(lambda: self._ir(self.fila + 1))
        b_ajustar = QPushButton("Ajustar")
        b_ajustar.setToolTip("Ver la hoja entera (Ctrl + rueda acerca y aleja)")
        b_ajustar.clicked.connect(self.lienzo.ajustar)
        b_mas = QPushButton("+")
        b_mas.clicked.connect(lambda: self.lienzo.acercar(1.25))
        b_menos = QPushButton("−")
        b_menos.clicked.connect(lambda: self.lienzo.acercar(0.8))
        for w in (self.btn_antes, self.etiqueta, self.btn_despues, b_ajustar, b_menos, b_mas):
            pie.addWidget(w)
        pie.addStretch()
        self.btn_todas = QPushButton("Copiar a todas las hojas")
        self.btn_todas.setToolTip("Pone las marcas seleccionadas en el mismo sitio de todas las demás hojas (un sello, una firma, un encabezado)")
        self.btn_todas.clicked.connect(self._a_todas)
        self.btn_sin_recorte = QPushButton("Quitar recorte")
        self.btn_sin_recorte.clicked.connect(self._quitar_recorte)
        self.btn_recorte_todas = QPushButton("Recortar todas igual")
        self.btn_recorte_todas.setToolTip("Aplica este mismo recorte a todas las hojas")
        self.btn_recorte_todas.clicked.connect(self._recorte_a_todas)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        aceptar = QPushButton("Aceptar")
        aceptar.setDefault(True)
        aceptar.clicked.connect(self._aceptar)
        for w in (self.btn_todas, self.btn_sin_recorte, self.btn_recorte_todas, cancelar, aceptar):
            pie.addWidget(w)
        col.addLayout(pie)

        for atajo, funcion in (("Ctrl+Z", self.lienzo.deshacer), ("Ctrl+Y", self.lienzo.rehacer), ("Ctrl+C", self.lienzo.copiar),
                               ("Ctrl+V", self.lienzo.pegar), ("PgUp", lambda: self._ir(self.fila - 1)),
                               ("PgDown", lambda: self._ir(self.fila + 1)), ("Ctrl+0", self.lienzo.ajustar)):
            a = QAction(self)
            a.setShortcut(QKeySequence(atajo))
            a.triggered.connect(funcion)
            self.addAction(a)
        self._elegir("seleccionar")

    # ------------------------------------------------------------------ páginas
    def _estado_de(self, fila: int) -> tuple:
        if fila in self.trabajo:
            return self.trabajo[fila]
        p = self.documento.paginas[fila]
        return p.marcas, p.recorte

    def _recoger(self) -> None:
        """Lo que hay en el lienzo pasa a la copia de trabajo de su hoja."""
        self.lienzo.terminar_texto()
        estado = self.lienzo.estado()
        p = self.documento.paginas[self.fila]
        if estado != (p.marcas, p.recorte) or self.fila in self.trabajo:
            self.trabajo[self.fila] = estado

    def _cargar(self, fila: int) -> None:
        self.fila = fila
        marcas, recorte = self._estado_de(fila)
        self.lienzo.cargar(self.documento.paginas[fila], marcas, recorte)
        self._refrescar()

    def _ir(self, fila: int) -> None:
        if 0 <= fila < len(self.documento):
            self._recoger()
            self._cargar(fila)

    def _refrescar(self) -> None:
        n = len(self.documento)
        p = self.documento.paginas[self.fila]
        self.etiqueta.setText(f"  Hoja {self.fila + 1} de {n} · {p.etiqueta}  ")
        self.btn_antes.setEnabled(self.fila > 0)
        self.btn_despues.setEnabled(self.fila < n - 1)
        self.btn_deshacer.setEnabled(bool(self.lienzo._pila))
        self.btn_rehacer.setEnabled(bool(self.lienzo._futuro))
        self.btn_sin_recorte.setVisible(self.lienzo.recorte is not None)
        self.btn_recorte_todas.setVisible(self.lienzo.recorte is not None and n > 1)
        self.btn_todas.setVisible(n > 1)
        self.btn_todas.setEnabled(bool(self.lienzo.elegidos()))

    # ------------------------------------------------------------------ herramientas y propiedades
    def _elegir(self, nombre: str) -> None:
        if nombre == "imagen":
            self.acciones[self.lienzo.herramienta].setChecked(True)
            ruta, _ = QFileDialog.getOpenFileName(self, "Elegir imagen", carpeta_inicial("carpeta_imagen", Path.home() / "Pictures"), FILTRO_IMAGEN)
            if ruta:
                recordar_carpeta("carpeta_imagen", ruta)
                if not self.lienzo.poner_imagen(Path(ruta).read_bytes()):
                    QMessageBox.warning(self, APP_NAME, "No se pudo leer esa imagen.")
            return
        self.acciones[nombre].setChecked(True)
        self.lienzo.fijar_herramienta(nombre)
        self.pista.setText(next(ayuda for n, _, _, ayuda in HERRAMIENTAS if n == nombre))
        self._pintar_color()

    def _pintar_color(self) -> None:
        elegidos = self.lienzo.elegidos()
        c = None
        if elegidos:
            m = elegidos[0].marca
            c = getattr(m, "color", None) or getattr(m, "relleno", None) or getattr(m, "borde", None)
        c = c or self.lienzo.colores.get(self.lienzo.herramienta)
        self.btn_color.setEnabled(c is not None)
        self.btn_color.setStyleSheet(f"QPushButton {{ border-bottom: 4px solid #{c}; }}" if c else "")

    def _color(self) -> None:
        elegidos = self.lienzo.elegidos()
        actual = self.lienzo.colores.get(self.lienzo.herramienta, "000000")
        q = QColorDialog.getColor(QColor("#" + actual), self, "Color")
        if not q.isValid():
            return
        if elegidos:
            self.lienzo.cambiar_elegidos(color=_hex(q))
        elif self.lienzo.herramienta in self.lienzo.colores:
            self.lienzo.colores[self.lienzo.herramienta] = _hex(q)
        self._pintar_color()

    def _prop(self, clave: str, valor) -> None:
        self.lienzo.props[clave] = valor
        self.lienzo.cambiar_elegidos(**{clave: valor})

    def _seleccion(self) -> None:
        """Al elegir un texto, los controles enseñan su letra."""
        elegidos = self.lienzo.elegidos()
        if len(elegidos) == 1 and isinstance(elegidos[0].marca, Texto):
            m = elegidos[0].marca
            for control, fijar in ((self.cuerpo, lambda: self.cuerpo.setValue(m.cuerpo)),
                                   (self.fuente, lambda: self.fuente.setCurrentIndex(max(0, self.fuente.findData(m.fuente)))),
                                   (self.negrita, lambda: self.negrita.setChecked(m.negrita)),
                                   (self.cursiva, lambda: self.cursiva.setChecked(m.cursiva))):
                control.blockSignals(True)
                fijar()
                control.blockSignals(False)
            self.lienzo.props.update(cuerpo=m.cuerpo, fuente=m.fuente, negrita=m.negrita, cursiva=m.cursiva)
        self._pintar_color()
        self._refrescar()

    # ------------------------------------------------------------------ a todas las hojas
    def _a_todas(self) -> None:
        marcas = [it.marca for it in self.lienzo.elegidos()]
        if not marcas:
            return
        self._recoger()
        for fila in range(len(self.documento)):
            if fila != self.fila:
                previas, recorte = self._estado_de(fila)
                self.trabajo[fila] = (tuple(previas) + tuple(marcas), recorte)
        QMessageBox.information(self, APP_NAME, f"Copiado a las otras {len(self.documento) - 1} hojas, en el mismo sitio.")

    def _quitar_recorte(self) -> None:
        if self.lienzo.recorte is not None:
            self.lienzo.antes()
            self.lienzo.recorte = None
            self.lienzo.scene().update()
            self._refrescar()

    def _recorte_a_todas(self) -> None:
        rc = self.lienzo.recorte
        if rc is None:
            return
        self._recoger()
        hechas = 0
        for fila, p in enumerate(self.documento.paginas):
            if fila == self.fila:
                continue
            ancho, alto = p.tamano_base
            x0, y0, x1, y1 = max(0.0, rc[0]), max(0.0, rc[1]), min(ancho, rc[0] + rc[2]), min(alto, rc[1] + rc[3])
            if x1 - x0 >= 18 and y1 - y0 >= 18:
                self.trabajo[fila] = (self._estado_de(fila)[0], (x0, y0, x1 - x0, y1 - y0))
                hechas += 1
        QMessageBox.information(self, APP_NAME, f"El mismo recorte queda en otras {hechas} hojas.")

    # ------------------------------------------------------------------ resultado
    def _aceptar(self) -> None:
        self._recoger()
        self.accept()

    def cambios(self) -> dict[int, Pagina]:
        salida = {}
        for fila, (marcas, recorte) in self.trabajo.items():
            p = self.documento.paginas[fila]
            nueva = replace(p, marcas=tuple(marcas), recorte=recorte)
            if nueva != p:
                salida[fila] = nueva
        return salida

    def reject(self) -> None:
        self._recoger()
        if self.cambios():
            respuesta = QMessageBox.question(self, APP_NAME, "¿Descartar lo que has hecho en el editor?")
            if respuesta != QMessageBox.StandardButton.Yes:
                return
        super().reject()
