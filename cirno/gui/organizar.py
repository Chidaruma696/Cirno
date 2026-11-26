"""Pestaña «Organizar y editar»: juntar varios PDF (e imágenes), ordenar las hojas
arrastrándolas, girarlas, quitarlas, duplicarlas, editarlas (texto, resaltar, tapar, firmar,
recortar), numerarlas, ponerles marca de agua, y guardar el resultado en un PDF nuevo o
repartido en varios, con contraseña o más ligero si hace falta."""

from __future__ import annotations

import queue
import shutil
import tempfile
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QProgressBar, QRadioButton, QSlider, QSpinBox, QStyle, QStyledItemDelegate, QToolBar, QToolButton, QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..pdf import render
from ..pdf.documento import Documento, Pagina
from ..pdf.guardar import (
    ErrorGuardar, OpcionesPdf, dividir, grupos_cada, grupos_por_inicio, guardar, imagen_a_pdf, inicios_de_documento,
    nombres_division,
)
from ..pdf.marcas import colocar, marca_de_agua, numero_de_pagina
from .comun import a_qimage, abrir_en_sistema, carpeta_inicial, pedir_clave, recordar_carpeta
from .editor import EditorPagina
from .pintura import pintar_marcas

PASOS_MINIATURA = (160, 260, 420)  # tamaños a los que se pintan las miniaturas, según el zoom
MAX_MINIATURAS = 900  # las que se guardan en memoria; las menos usadas se repintan si hacen falta
FILTRO_ABRIR = "PDF e imágenes (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif);;PDF (*.pdf);;Todos (*)"
FORMATOS_NUMERO = ("Página {n} de {t}", "{n} de {t}", "{n} / {t}", "{n}", "- {n} -", "Hoja {n}")
POSICIONES = (("Abajo, al centro", "abajo-centro"), ("Abajo, a la derecha", "abajo-der"), ("Abajo, a la izquierda", "abajo-izq"),
              ("Arriba, al centro", "arriba-centro"), ("Arriba, a la derecha", "arriba-der"), ("Arriba, a la izquierda", "arriba-izq"))
COLORES_AGUA = (("Rojo", "B71C1C"), ("Gris", "616161"), ("Azul", "0D47A1"), ("Verde", "1B5E20"))


class HiloMiniaturas(QThread):
    """Pinta miniaturas fuera del hilo de la ventana. Lo último que se pide sale primero, que es
    lo que el usuario tiene delante."""

    lista = Signal(object, int, int, object)  # fuente, índice, lado, QImage

    def __init__(self) -> None:
        super().__init__()
        self._cola: queue.LifoQueue = queue.LifoQueue()
        self._activo = True

    def pedir(self, fuente: render.Fuente, indice: int, lado: int) -> None:
        self._cola.put((fuente, indice, lado))

    def parar(self) -> None:
        self._activo = False
        self._cola.put(None)
        self.wait(3000)

    def run(self) -> None:
        while self._activo:
            pedido = self._cola.get()
            if pedido is None or not self._activo:
                break
            fuente, indice, lado = pedido
            try:
                imagen = a_qimage(render.pintar(fuente, indice, lado_max=lado))
            except Exception:  # noqa: BLE001 - una página que PDFium no pinta se queda en blanco
                continue
            self.lista.emit(fuente, indice, lado, imagen)


class Tarea(QThread):
    """Ejecuta una función larga (guardar, dividir) sin congelar la ventana."""

    avance = Signal(int, int)
    hecho = Signal(object)
    fallo = Signal(str)

    def __init__(self, funcion) -> None:
        super().__init__()
        self._funcion = funcion

    def run(self) -> None:
        try:
            self.hecho.emit(self._funcion(self.avance.emit))
        except ErrorGuardar as e:
            self.fallo.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.fallo.emit(f"{type(e).__name__}: {e}")


def pintar_hoja(painter: QPainter, pagina: Pagina, mapa: QPixmap | None, zona: QRect, borde: QColor) -> None:
    """La hoja tal como quedará: recortada, girada y con sus marcas, encajada en `zona`."""
    ancho, alto = pagina.tamano
    escala = min(zona.width() / max(ancho, 1), zona.height() / max(alto, 1))
    hoja = QRect(0, 0, max(int(ancho * escala), 4), max(int(alto * escala), 4))
    hoja.moveCenter(zona.center())
    painter.save()
    painter.fillRect(hoja, Qt.GlobalColor.white)
    painter.setClipRect(hoja)
    zx, zy, zw, zh = pagina.zona
    base_ancho, base_alto = pagina.tamano_base
    centro = hoja.center()
    painter.translate(centro.x() + 0.5, centro.y() + 0.5)
    painter.rotate(pagina.rotacion)
    painter.scale(escala, escala)
    painter.translate(-(zx + zw / 2), -(zy + zh / 2))
    if mapa is not None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(QRectF(0, 0, base_ancho, base_alto), mapa, QRectF(mapa.rect()))
    pintar_marcas(painter, pagina.marcas)
    painter.restore()
    painter.setPen(QPen(borde, 1))
    painter.drawRect(hoja.adjusted(0, 0, -1, -1))


class DelegadoPagina(QStyledItemDelegate):
    def __init__(self, vista: "VistaPaginas") -> None:
        super().__init__(vista)
        self.vista = vista

    def paint(self, painter: QPainter, option, index) -> None:
        vista = self.vista
        fila = index.row()
        if fila >= len(vista.documento.paginas):
            return
        pagina = vista.documento.paginas[fila]
        r: QRect = option.rect.adjusted(4, 4, -4, -4)
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            fondo = QColor(option.palette.highlight().color())
            fondo.setAlpha(70)
            painter.fillRect(r, fondo)
            painter.setPen(QPen(option.palette.highlight().color(), 2))
            painter.drawRect(r.adjusted(1, 1, -1, -1))

        zona = QRect(r.left() + 8, r.top() + 8, r.width() - 16, r.height() - 46)
        pintar_hoja(painter, pagina, vista.miniatura(pagina, max(zona.width(), zona.height())), zona, option.palette.mid().color())

        painter.setPen(option.palette.text().color())
        letra = painter.font()
        letra.setBold(True)
        painter.setFont(letra)
        numero = f"{fila + 1}  ✎" if pagina.editada else str(fila + 1)
        painter.drawText(QRect(r.left(), zona.bottom() + 4, r.width(), 16), Qt.AlignmentFlag.AlignCenter, numero)
        letra.setBold(False)
        letra.setPointSizeF(max(letra.pointSizeF() - 1, 7))
        painter.setFont(letra)
        painter.setPen(option.palette.placeholderText().color())
        pie = painter.fontMetrics().elidedText(pagina.etiqueta, Qt.TextElideMode.ElideMiddle, r.width() - 8)
        painter.drawText(QRect(r.left(), zona.bottom() + 20, r.width(), 16), Qt.AlignmentFlag.AlignCenter, pie)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return self.vista.gridSize()


class VistaPaginas(QListWidget):
    """La rejilla de hojas. Cada elemento es una fila del `Documento`; no guarda nada propio."""

    movidas = Signal(list, int)  # filas, fila delante de la cual caen
    soltados = Signal(list, int)  # rutas de archivos, fila delante de la cual caen
    abrir_pagina = Signal(int)

    def __init__(self, documento: Documento, hilo: HiloMiniaturas) -> None:
        super().__init__()
        self.documento = documento
        self.hilo = hilo
        self._cache: OrderedDict[tuple[int, int], tuple[QPixmap, int]] = OrderedDict()
        self._pedidas: set[tuple[int, int, int]] = set()
        self._marca: int | None = None
        self.lado = 170
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(DelegadoPagina(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fijar_lado(self.lado)
        self.itemDoubleClicked.connect(lambda it: self.abrir_pagina.emit(self.row(it)))
        hilo.lista.connect(self._llego)

    # ------------------------------------------------------------------ contenido
    def fijar_lado(self, lado: int) -> None:
        self.lado = lado
        self.setGridSize(QSize(lado + 28, lado + 62))
        self.viewport().update()

    def sincronizar(self, seleccion: list[int] | None = None) -> None:
        """Deja tantos elementos como páginas tiene el documento y marca las filas dadas."""
        n = len(self.documento.paginas)
        self.blockSignals(True)
        while self.count() > n:
            self.takeItem(self.count() - 1)
        while self.count() < n:
            self.addItem(QListWidgetItem())
        self.clearSelection()
        for f in seleccion or []:
            if 0 <= f < n:
                self.item(f).setSelected(True)
        if seleccion:
            self.setCurrentRow(seleccion[0], self.selectionModel().SelectionFlag.NoUpdate)
            self.scrollToItem(self.item(min(seleccion[0], n - 1)))
        self.blockSignals(False)
        self.itemSelectionChanged.emit()
        self.viewport().update()

    def filas(self) -> list[int]:
        return sorted(self.row(it) for it in self.selectedItems())

    # ------------------------------------------------------------------ miniaturas
    def miniatura(self, pagina: Pagina, lado: int) -> QPixmap | None:
        clave = (id(pagina.fuente), pagina.indice)
        paso = next((p for p in PASOS_MINIATURA if p >= lado), PASOS_MINIATURA[-1])
        tenida = self._cache.get(clave)
        if tenida is not None:
            self._cache.move_to_end(clave)
        if tenida is None or tenida[1] < paso:
            pedido = (*clave, paso)
            if pedido not in self._pedidas:
                self._pedidas.add(pedido)
                self.hilo.pedir(pagina.fuente, pagina.indice, paso)
        return tenida[0] if tenida else None

    def _llego(self, fuente, indice: int, lado: int, imagen) -> None:
        clave = (id(fuente), indice)
        self._pedidas.discard((*clave, lado))
        tenida = self._cache.get(clave)
        if tenida is None or tenida[1] <= lado:
            self._cache[clave] = (QPixmap.fromImage(imagen), lado)
            self._cache.move_to_end(clave)
            while len(self._cache) > MAX_MINIATURAS:
                self._cache.popitem(last=False)
        self.viewport().update()

    # ------------------------------------------------------------------ arrastrar
    def _fila_destino(self, pos: QPoint) -> int:
        """La fila delante de la cual caería lo que se suelta en `pos`."""
        indice = self.indexAt(pos)
        if indice.isValid():
            r = self.visualRect(indice)
            return indice.row() + (1 if pos.x() > r.center().x() else 0)
        ultimo_de_la_fila = None
        for i in range(self.count()):
            r = self.visualRect(self.model().index(i, 0))
            if r.top() <= pos.y() <= r.bottom():
                if pos.x() < r.center().x():
                    return i
                ultimo_de_la_fila = i
            elif r.top() > pos.y():
                break
        return self.count() if ultimo_de_la_fila is None else ultimo_de_la_fila + 1

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls() or e.source() is self:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls() or e.source() is self:
            super().dragMoveEvent(e)  # para que la vista se desplace sola al acercarse al borde
            self._marca = self._fila_destino(e.position().toPoint())
            self.viewport().update()
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self._marca = None
        self.viewport().update()
        super().dragLeaveEvent(e)

    def dropEvent(self, e) -> None:  # noqa: N802
        destino = self._fila_destino(e.position().toPoint())
        self._marca = None
        self.viewport().update()
        if e.source() is self:
            # La vista no mueve nada por su cuenta: manda el documento y luego se sincroniza.
            e.setDropAction(Qt.DropAction.IgnoreAction)
            e.accept()
            self.movidas.emit(self.filas(), destino)
        elif e.mimeData().hasUrls():
            rutas = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()
            if rutas:
                self.soltados.emit(rutas, destino)
        else:
            e.ignore()

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        if self.count() == 0:
            p = QPainter(self.viewport())
            p.setPen(self.palette().placeholderText().color())
            letra = p.font()
            letra.setPointSizeF(letra.pointSizeF() + 2)
            p.setFont(letra)
            p.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter,
                       "Arrastra aquí los PDF (o imágenes) que quieras juntar o editar\n\n"
                       "Mueve las hojas con el ratón para ordenarlas · doble clic en una hoja para editarla\n"
                       "y pulsa «Guardar PDF»")
            p.end()
        elif self._marca is not None:
            n = self.count()
            if self._marca < n:
                r = self.visualRect(self.model().index(self._marca, 0))
                x = r.left()
            else:
                r = self.visualRect(self.model().index(n - 1, 0))
                x = r.right()
            p = QPainter(self.viewport())
            p.setPen(QPen(self.palette().highlight().color(), 3))
            p.drawLine(x, r.top() + 6, x, r.bottom() - 6)
            p.end()


def _botones(dialogo: QDialog, aceptar: str) -> QDialogButtonBox:
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    botones.button(QDialogButtonBox.StandardButton.Ok).setText(aceptar)
    botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
    botones.accepted.connect(dialogo.accept)
    botones.rejected.connect(dialogo.reject)
    return botones


def _combo_cuales(total: int, elegidas: int) -> QComboBox:
    combo = QComboBox()
    combo.addItem(f"Todas las hojas ({total})", "todas")
    if elegidas:
        combo.addItem(f"Solo las seleccionadas ({elegidas})", "elegidas")
        if elegidas > 1:
            combo.setCurrentIndex(1)
    return combo


class DialogoDividir(QDialog):
    def __init__(self, padre: QWidget, total: int, elegidas: int, base: str, carpeta: str) -> None:
        super().__init__(padre)
        self.setWindowTitle("Dividir en varios PDF")
        forma = QFormLayout(self)
        self.cuales = _combo_cuales(total, elegidas)
        forma.addRow("Hojas:", self.cuales)
        self.una = QRadioButton("Un PDF por cada hoja")
        self.varias = QRadioButton("Un PDF cada")
        self.listo = QRadioButton("Un PDF por documento: donde el texto diga «Página 1 de N»")
        self.listo.setToolTip("Para un lote de facturas, recibos o contratos escaneados o impresos juntos: Cirno busca en cada hoja "
                              "«Página 1 de…», «Hoja 1/…» o «Pág. 1 de…» y corta ahí.")
        self.una.setChecked(True)
        self.cada = QSpinBox()
        self.cada.setRange(2, 9999)
        self.cada.setSuffix(" hojas")
        self.cada.setEnabled(False)
        self.varias.toggled.connect(self.cada.setEnabled)
        fila = QHBoxLayout()
        fila.addWidget(self.varias)
        fila.addWidget(self.cada)
        fila.addStretch()
        forma.addRow(self.una)
        forma.addRow(fila)
        forma.addRow(self.listo)
        self.base = QLineEdit(base)
        forma.addRow("Nombre:", self.base)
        self.carpeta = QLineEdit(carpeta)
        elegir = QAction("Elegir…", self)
        elegir.triggered.connect(self._elegir)
        self.carpeta.addAction(elegir, QLineEdit.ActionPosition.TrailingPosition)
        forma.addRow("Carpeta:", self.carpeta)
        self.nota = QLabel("")
        self.nota.setWordWrap(True)
        forma.addRow(self.nota)
        forma.addRow(_botones(self, "Dividir"))
        self._total, self._elegidas = total, elegidas
        for senal in (self.cuales.currentIndexChanged, self.una.toggled, self.listo.toggled, self.cada.valueChanged, self.base.textChanged):
            senal.connect(self._actualizar)
        self._actualizar()

    def _elegir(self) -> None:
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.carpeta.text())
        if ruta:
            self.carpeta.setText(ruta)

    def paso(self) -> int:
        return 1 if self.una.isChecked() else self.cada.value()

    def _actualizar(self) -> None:
        n = self._elegidas if self.cuales.currentData() == "elegidas" else self._total
        base = self.base.text().strip() or "parte"
        if self.listo.isChecked():
            self.nota.setText(f"Los archivos se llamarán {base}-01.pdf, {base}-02.pdf… Si ninguna hoja dice «Página 1 de N», no se divide nada.")
            return
        nombres = nombres_division(len(grupos_cada(list(range(n)), self.paso())), Path("."), base)
        self.nota.setText(f"Saldrán {len(nombres)} archivos: {nombres[0].name} … {nombres[-1].name}"
                          if len(nombres) > 1 else f"Saldrá 1 archivo: {nombres[0].name}")


class DialogoNumerar(QDialog):
    def __init__(self, padre: QWidget, total: int, elegidas: int) -> None:
        super().__init__(padre)
        self.setWindowTitle("Numerar las hojas")
        forma = QFormLayout(self)
        self.cuales = _combo_cuales(total, elegidas)
        forma.addRow("Hojas:", self.cuales)
        self.formato = QComboBox()
        for f in FORMATOS_NUMERO:
            self.formato.addItem(f.format(n=1, t=total), f)
        forma.addRow("Formato:", self.formato)
        self.posicion = QComboBox()
        for texto, clave in POSICIONES:
            self.posicion.addItem(texto, clave)
        forma.addRow("Dónde:", self.posicion)
        self.primero = QSpinBox()
        self.primero.setRange(0, 99999)
        self.primero.setValue(1)
        forma.addRow("Empezar en:", self.primero)
        self.cuerpo = QDoubleSpinBox()
        self.cuerpo.setRange(5, 40)
        self.cuerpo.setDecimals(1)
        self.cuerpo.setValue(9)
        self.cuerpo.setSuffix(" pt")
        forma.addRow("Tamaño:", self.cuerpo)
        self.margen = QSpinBox()
        self.margen.setRange(6, 200)
        self.margen.setValue(24)
        self.margen.setSuffix(" pt")
        forma.addRow("Margen:", self.margen)
        forma.addRow(_botones(self, "Numerar"))


class DialogoAgua(QDialog):
    def __init__(self, padre: QWidget, total: int, elegidas: int) -> None:
        super().__init__(padre)
        self.setWindowTitle("Marca de agua")
        forma = QFormLayout(self)
        self.cuales = _combo_cuales(total, elegidas)
        forma.addRow("Hojas:", self.cuales)
        self.texto = QComboBox()
        self.texto.setEditable(True)
        self.texto.addItems(["COPIA", "BORRADOR", "CONFIDENCIAL", "CANCELADO", "PAGADO", "SIN VALOR"])
        forma.addRow("Texto:", self.texto)
        self.color = QComboBox()
        for nombre, valor in COLORES_AGUA:
            self.color.addItem(nombre, valor)
        forma.addRow("Color:", self.color)
        self.fuerza = QSlider(Qt.Orientation.Horizontal)
        self.fuerza.setRange(5, 60)
        self.fuerza.setValue(18)
        forma.addRow("Intensidad:", self.fuerza)
        forma.addRow(_botones(self, "Poner"))


class DialogoOpciones(QDialog):
    def __init__(self, padre: QWidget, op: OpcionesPdf) -> None:
        super().__init__(padre)
        self.setWindowTitle("Opciones del PDF que se guarda")
        self.setMinimumWidth(460)
        forma = QFormLayout(self)
        self.clave = QLineEdit(op.clave)
        self.clave.setEchoMode(QLineEdit.EchoMode.Password)
        self.clave.setPlaceholderText("Vacío = sin contraseña")
        ver = QCheckBox("Ver")
        ver.toggled.connect(lambda si: self.clave.setEchoMode(QLineEdit.EchoMode.Normal if si else QLineEdit.EchoMode.Password))
        fila = QHBoxLayout()
        fila.addWidget(self.clave, 1)
        fila.addWidget(ver)
        forma.addRow("Contraseña para abrirlo:", fila)
        self.reducir = QComboBox()
        for texto, clave in (("No, dejar las imágenes como están", ""), ("Para pantalla (lo más ligero)", "pantalla"),
                             ("Para mandar por correo", "correo"), ("Para imprimir", "impresion")):
            self.reducir.addItem(texto, clave)
        self.reducir.setCurrentIndex(max(0, self.reducir.findData(op.reducir)))
        self.reducir.setToolTip("Baja la resolución de las imágenes grandes (escaneos, fotos) y las recomprime. El texto no se toca.")
        forma.addRow("Reducir el tamaño:", self.reducir)
        self.titulo, self.autor, self.asunto, self.palabras = (QLineEdit(v) for v in (op.titulo, op.autor, op.asunto, op.palabras))
        forma.addRow("Título:", self.titulo)
        forma.addRow("Autor:", self.autor)
        forma.addRow("Asunto:", self.asunto)
        forma.addRow("Palabras clave:", self.palabras)
        nota = QLabel("Se aplican cada vez que guardes o dividas, hasta que las cambies. Si no pones título ni autor y todo "
                      "sale de un solo PDF, se conservan los que tenía.")
        nota.setWordWrap(True)
        nota.setEnabled(False)
        forma.addRow(nota)
        forma.addRow(_botones(self, "Aceptar"))

    def opciones(self) -> OpcionesPdf:
        return OpcionesPdf(self.titulo.text().strip(), self.autor.text().strip(), self.asunto.text().strip(),
                           self.palabras.text().strip(), self.clave.text(), self.reducir.currentData())


class PestanaOrganizar(QWidget):
    estado = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.documento = Documento()
        self.opciones = OpcionesPdf()
        self.hilo = HiloMiniaturas()
        self.hilo.start()
        self.tarea: Tarea | None = None
        self._temporal: Path | None = None
        self._n_temporales = 0
        self._construir()
        self._refrescar()

    # ------------------------------------------------------------------ construcción
    def _accion(self, texto: str, funcion, atajo=None, ayuda: str = "") -> QAction:
        a = QAction(texto, self)
        a.triggered.connect(funcion)
        if atajo:
            a.setShortcut(QKeySequence(atajo))
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        if ayuda:
            a.setToolTip(ayuda + (f" ({QKeySequence(atajo).toString(QKeySequence.SequenceFormat.NativeText)})" if atajo else ""))
        self.addAction(a)
        return a

    def _boton_menu(self, barra: QToolBar, texto: str, acciones) -> QToolButton:
        boton = QToolButton()
        boton.setText(texto)
        boton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(boton)
        for a in acciones:
            menu.addSeparator() if a is None else menu.addAction(a)
        boton.setMenu(menu)
        barra.addWidget(boton)
        return boton

    def _construir(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(6)

        self.a_anadir = self._accion("Añadir…", self.elegir_archivos, "Ctrl+O", "Añadir PDF o imágenes al final")
        self.a_guardar = self._accion("Guardar PDF…", self.guardar, "Ctrl+S", "Guardar todas las hojas, en este orden, en un PDF nuevo")
        self.a_seleccion = self._accion("Guardar selección…", self.guardar_seleccion, "Ctrl+Shift+S",
                                        "Guardar solo las hojas seleccionadas en un PDF nuevo")
        self.a_dividir = self._accion("Dividir…", self.dividir, None, "Repartir las hojas en varios PDF")
        self.a_editar = self._accion("Editar", self.editar, "Return", "Abrir la hoja en el editor: escribir, corregir texto, resaltar, tapar, firmar, recortar")
        self.a_izquierda = self._accion("Girar ↺", lambda: self.girar(-90), "Ctrl+L", "Girar a la izquierda")
        self.a_derecha = self._accion("Girar ↻", lambda: self.girar(90), "Ctrl+R", "Girar a la derecha")
        self.a_duplicar = self._accion("Duplicar", self.duplicar, "Ctrl+D", "Duplicar las hojas seleccionadas")
        self.a_eliminar = self._accion("Quitar", self.eliminar, "Del", "Quitar las hojas seleccionadas (el archivo original no se toca)")
        self.a_deshacer = self._accion("Deshacer", self.deshacer, "Ctrl+Z", "Deshacer")
        self.a_rehacer = self._accion("Rehacer", self.rehacer, "Ctrl+Y", "Rehacer")
        self.a_vaciar = self._accion("Vaciar", self.vaciar, None, "Quitar todas las hojas y empezar de nuevo")
        # Herramientas
        self.a_numerar = self._accion("Numerar las hojas…", self.numerar)
        self.a_agua = self._accion("Marca de agua…", self.agua)
        self.a_intercalar = self._accion("Intercalar caras y dorsos…", self.intercalar)
        self.a_invertir = self._accion("Invertir el orden", self.invertir)
        self.a_limpiar = self._accion("Quitar lo editado de las hojas seleccionadas", self.limpiar_edicion)
        self.a_opciones = self._accion("Contraseña, tamaño y propiedades…", self.elegir_opciones)
        # Seleccionar
        self.a_todo = self._accion("Todas", lambda: self.vista.selectAll(), "Ctrl+A")
        self.a_impares = self._accion("Las impares (1, 3, 5…)", lambda: self._elegir(lambda i, p: i % 2 == 0))
        self.a_pares = self._accion("Las pares (2, 4, 6…)", lambda: self._elegir(lambda i, p: i % 2 == 1))
        self.a_blancas = self._accion("Las que están en blanco", self.elegir_blancas)
        self.a_archivo = self._accion("Las del mismo archivo", self.elegir_mismo_archivo)
        self.a_editadas = self._accion("Las editadas", lambda: self._elegir(lambda i, p: p.editada))
        self.a_apaisadas = self._accion("Las apaisadas", lambda: self._elegir(lambda i, p: p.tamano[0] > p.tamano[1]))

        barra = QToolBar()
        barra.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        barra.setMovable(False)
        for a in (self.a_anadir, self.a_guardar, self.a_seleccion, self.a_dividir):
            barra.addAction(a)
        barra.addSeparator()
        for a in (self.a_editar, self.a_izquierda, self.a_derecha, self.a_duplicar, self.a_eliminar):
            barra.addAction(a)
        barra.addSeparator()
        self.btn_herramientas = self._boton_menu(barra, "Herramientas", (
            self.a_numerar, self.a_agua, None, self.a_intercalar, self.a_invertir, None, self.a_limpiar, None, self.a_opciones))
        self.btn_seleccionar = self._boton_menu(barra, "Seleccionar", (
            self.a_todo, self.a_impares, self.a_pares, None, self.a_blancas, self.a_apaisadas, self.a_editadas, self.a_archivo))
        barra.addSeparator()
        for a in (self.a_deshacer, self.a_rehacer, self.a_vaciar):
            barra.addAction(a)
        barra.addSeparator()
        barra.addWidget(QLabel(" Tamaño "))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(90, 420)
        self.zoom.setValue(170)
        self.zoom.setFixedWidth(110)
        barra.addWidget(self.zoom)
        col.addWidget(barra)

        self.vista = VistaPaginas(self.documento, self.hilo)
        self.vista.movidas.connect(self._mover)
        self.vista.soltados.connect(self.anadir)
        self.vista.abrir_pagina.connect(self.editar)
        self.vista.itemSelectionChanged.connect(self._refrescar)
        self.vista.customContextMenuRequested.connect(self._menu)
        self.zoom.valueChanged.connect(self.vista.fijar_lado)
        col.addWidget(self.vista, 1)

        pie = QHBoxLayout()
        self.etiqueta = QLabel("")
        pie.addWidget(self.etiqueta, 1)
        self.barra_progreso = QProgressBar()
        self.barra_progreso.setFixedWidth(220)
        self.barra_progreso.setVisible(False)
        pie.addWidget(self.barra_progreso)
        col.addLayout(pie)

    def _menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        for a in (self.a_editar, None, self.a_izquierda, self.a_derecha, self.a_duplicar, self.a_eliminar, None,
                  self.a_numerar, self.a_agua, self.a_limpiar, None, self.a_seleccion, self.a_archivo, self.a_todo):
            menu.addSeparator() if a is None else menu.addAction(a)
        menu.exec(self.vista.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ estado
    def _refrescar(self) -> None:
        n = len(self.documento)
        elegidas = len(self.vista.filas())
        ocupado = self.tarea is not None and self.tarea.isRunning()
        self.a_anadir.setEnabled(not ocupado)
        for a in (self.a_guardar, self.a_dividir, self.a_vaciar, self.a_numerar, self.a_agua, self.a_blancas, self.a_impares,
                  self.a_pares, self.a_todo, self.a_editadas, self.a_apaisadas):
            a.setEnabled(n > 0 and not ocupado)
        for a in (self.a_invertir, self.a_intercalar):
            a.setEnabled(n > 1 and not ocupado)
        for a in (self.a_seleccion, self.a_izquierda, self.a_derecha, self.a_duplicar, self.a_eliminar, self.a_archivo):
            a.setEnabled(elegidas > 0 and not ocupado)
        self.a_limpiar.setEnabled(any(self.documento.paginas[f].editada for f in self.vista.filas()) and not ocupado)
        self.a_editar.setEnabled(n > 0 and not ocupado)
        self.a_deshacer.setEnabled(self.documento.puede_deshacer and not ocupado)
        self.a_rehacer.setEnabled(self.documento.puede_rehacer and not ocupado)
        if n == 0:
            texto = "Sin hojas todavía"
        else:
            archivos = len({id(p.fuente) for p in self.documento.paginas})
            texto = f"{n} hojas de {archivos} archivos" if archivos != 1 else f"{n} hojas de 1 archivo"
            if n == 1:
                texto = "1 hoja"
            if elegidas:
                texto += f" · {elegidas} seleccionadas" if elegidas != 1 else " · 1 seleccionada"
        if self.opciones.resumen():
            texto += f"   |   Al guardar: {self.opciones.resumen()}"
        self.etiqueta.setText(texto)

    def _tras_cambio(self, seleccion: list[int] | None = None) -> None:
        self.vista.sincronizar(seleccion)
        self._refrescar()

    def hay_cambios(self) -> bool:
        return self.documento.modificado and len(self.documento) > 0

    # ------------------------------------------------------------------ añadir
    def elegir_archivos(self) -> None:
        rutas, _ = QFileDialog.getOpenFileNames(self, "Añadir PDF o imágenes", carpeta_inicial("carpeta_pdf", Path.home() / "Downloads"),
                                                FILTRO_ABRIR)
        if rutas:
            recordar_carpeta("carpeta_pdf", rutas[0])
            self.anadir(rutas)

    def _carpeta_temporal(self) -> Path:
        if self._temporal is None:
            self._temporal = Path(tempfile.mkdtemp(prefix="cirno-"))
        return self._temporal

    def _abrir(self, ruta: Path) -> render.Fuente | None:
        if ruta.suffix.lower() in render.EXT_IMAGEN:
            self._n_temporales += 1
            temporal = imagen_a_pdf(ruta, self._carpeta_temporal() / f"imagen-{self._n_temporales:04d}.pdf")
            return render.abrir(temporal, nombre=ruta.name, origen=ruta)
        clave = None
        while True:
            try:
                return render.abrir(ruta, clave=clave)
            except render.ClaveNecesaria:
                clave = pedir_clave(self, ruta.name, reintento=clave is not None)
                if clave is None:
                    return None

    def anadir(self, rutas, posicion: int | None = None) -> None:
        archivos: list[Path] = []
        for r in rutas:
            p = Path(r)
            if p.is_dir():
                archivos += sorted(x for x in p.iterdir() if x.suffix.lower() in render.EXT_PDF + render.EXT_IMAGEN)
            elif p.suffix.lower() in render.EXT_PDF + render.EXT_IMAGEN:
                archivos.append(p)
        if not archivos:
            return
        nuevas: list[Pagina] = []
        fallos: list[str] = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for ruta in archivos:
                try:
                    fuente = self._abrir(ruta)
                except (render.PdfIlegible, ErrorGuardar) as e:
                    fallos.append(str(e))
                    continue
                if fuente is not None:
                    nuevas += [Pagina(fuente, i) for i in range(fuente.n_paginas)]
        finally:
            QApplication.restoreOverrideCursor()
        filas = self.documento.insertar(nuevas, posicion)
        self._tras_cambio(filas)
        if fallos:
            QMessageBox.warning(self, APP_NAME, "No se pudieron abrir:\n\n" + "\n".join(fallos))

    # ------------------------------------------------------------------ operaciones
    def _mover(self, filas: list[int], destino: int) -> None:
        self._tras_cambio(self.documento.mover(filas, destino))

    def girar(self, grados: int) -> None:
        filas = self.vista.filas()
        self.documento.rotar(filas, grados)
        self._tras_cambio(filas)

    def duplicar(self) -> None:
        self._tras_cambio(self.documento.duplicar(self.vista.filas()))

    def eliminar(self) -> None:
        filas = self.vista.filas()
        if self.documento.eliminar(filas):
            n = len(self.documento)
            self._tras_cambio([min(filas[0], n - 1)] if n else None)

    def invertir(self) -> None:
        filas = self.vista.filas()
        self.documento.invertir(filas if len(filas) > 1 else None)
        self._tras_cambio(filas if len(filas) > 1 else None)

    def vaciar(self) -> None:
        self.documento.vaciar()
        self._tras_cambio()

    def deshacer(self) -> None:
        if self.documento.deshacer():
            self._tras_cambio()

    def rehacer(self) -> None:
        if self.documento.rehacer():
            self._tras_cambio()

    def editar(self, fila: int | bool | None = None) -> None:
        if not len(self.documento) or (self.tarea is not None and self.tarea.isRunning()):
            return
        if fila is None or isinstance(fila, bool):
            filas = self.vista.filas()
            fila = filas[0] if filas else 0
        editor = EditorPagina(self, self.documento, fila)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self.documento.reemplazar(editor.cambios())
        self._tras_cambio([editor.fila])

    def limpiar_edicion(self) -> None:
        filas = self.vista.filas()
        self.documento.reemplazar({f: replace(self.documento.paginas[f], marcas=(), recorte=None) for f in filas})
        self._tras_cambio(filas)

    # ------------------------------------------------------------------ herramientas
    def _objetivo(self, cuales: str) -> list[int]:
        return self.vista.filas() if cuales == "elegidas" else list(range(len(self.documento)))

    def numerar(self) -> None:
        filas = self.vista.filas()
        d = DialogoNumerar(self, len(self.documento), len(filas))
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        objetivo = self._objetivo(d.cuales.currentData())
        total = len(objetivo) + d.primero.value() - 1
        cambios = {}
        for k, f in enumerate(objetivo):
            p = self.documento.paginas[f]
            texto = d.formato.currentData().format(n=k + d.primero.value(), t=total)
            numero = numero_de_pagina(*p.tamano, texto, d.posicion.currentData(), d.cuerpo.value(), float(d.margen.value()))
            cambios[f] = replace(p, marcas=p.marcas + (colocar(numero, p.zona, p.rotacion),))
        self.documento.reemplazar(cambios)
        self._tras_cambio(objetivo if d.cuales.currentData() == "elegidas" else None)

    def agua(self) -> None:
        filas = self.vista.filas()
        d = DialogoAgua(self, len(self.documento), len(filas))
        if d.exec() != QDialog.DialogCode.Accepted or not d.texto.currentText().strip():
            return
        objetivo = self._objetivo(d.cuales.currentData())
        cambios = {}
        for f in objetivo:
            p = self.documento.paginas[f]
            marca = marca_de_agua(*p.tamano, d.texto.currentText().strip(), d.color.currentData(), d.fuerza.value() / 100.0)
            cambios[f] = replace(p, marcas=p.marcas + (colocar(marca, p.zona, p.rotacion),))
        self.documento.reemplazar(cambios)
        self._tras_cambio(objetivo if d.cuales.currentData() == "elegidas" else None)

    def intercalar(self) -> None:
        caja = QMessageBox(QMessageBox.Icon.Question, APP_NAME,
                           "Intercalar sirve cuando se escanearon primero todas las caras y luego todos los dorsos: la primera "
                           "mitad de las hojas son las caras y la segunda, los dorsos.\n\n¿En qué orden están los dorsos?", parent=self)
        orden = caja.addButton("En orden (2, 4, 6…)", QMessageBox.ButtonRole.AcceptRole)
        reves = caja.addButton("Al revés (…6, 4, 2)", QMessageBox.ButtonRole.AcceptRole)
        caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caja.exec()
        if caja.clickedButton() in (orden, reves):
            self.documento.intercalar(segunda_al_reves=caja.clickedButton() is reves)
            self._tras_cambio()

    def elegir_opciones(self) -> None:
        d = DialogoOpciones(self, self.opciones)
        if d.exec() == QDialog.DialogCode.Accepted:
            self.opciones = d.opciones()
            self._refrescar()

    # ------------------------------------------------------------------ seleccionar
    def _elegir(self, criterio) -> list[int]:
        filas = [i for i, p in enumerate(self.documento.paginas) if criterio(i, p)]
        self.vista.sincronizar(filas)
        self._refrescar()
        return filas

    def elegir_blancas(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            blancas = set()
            for i, p in enumerate(self.documento.paginas):
                try:
                    if not p.marcas and render.en_blanco(p.fuente, p.indice):
                        blancas.add(i)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            QApplication.restoreOverrideCursor()
        filas = self._elegir(lambda i, p: i in blancas)
        self.estado.emit(f"{len(filas)} hojas en blanco seleccionadas; «Quitar» las elimina" if filas else "No hay hojas en blanco")

    def elegir_mismo_archivo(self) -> None:
        fuentes = {id(self.documento.paginas[f].fuente) for f in self.vista.filas()}
        self._elegir(lambda i, p: id(p.fuente) in fuentes)

    # ------------------------------------------------------------------ guardar
    def _nombre_sugerido(self, paginas: list[Pagina]) -> str:
        origenes = list({id(p.fuente): p.fuente for p in paginas}.values())
        base = f"{origenes[0].origen.stem} - Cirno" if len(origenes) == 1 else "PDF unido"
        return str(Path(carpeta_inicial("carpeta_guardar", origenes[0].origen.parent)) / f"{base}.pdf")

    def _lanzar(self, funcion, al_terminar) -> None:
        self.tarea = Tarea(funcion)
        self.barra_progreso.setRange(0, 0)
        self.barra_progreso.setVisible(True)
        self.tarea.avance.connect(lambda hecho, total: (self.barra_progreso.setRange(0, total), self.barra_progreso.setValue(hecho)))
        self.tarea.hecho.connect(lambda resultado: (self._fin_tarea(), al_terminar(resultado)))
        self.tarea.fallo.connect(lambda mensaje: (self._fin_tarea(), QMessageBox.warning(self, APP_NAME, mensaje)))
        self.tarea.start()
        self._refrescar()

    def _fin_tarea(self) -> None:
        self.barra_progreso.setVisible(False)
        self.tarea.wait()
        self._refrescar()

    def _guardar(self, paginas: list[Pagina], todo: bool) -> None:
        if not paginas:
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar PDF", self._nombre_sugerido(paginas), "PDF (*.pdf)")
        if not ruta:
            return
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        recordar_carpeta("carpeta_guardar", ruta)
        opciones = self.opciones

        def listo(salida: Path) -> None:
            if todo:
                self.documento.modificado = False
            peso = salida.stat().st_size / 1_048_576
            self.estado.emit(f"Guardado: {salida} ({peso:.1f} MB)")
            self._preguntar_abrir(f"Guardado en\n{salida}\n\n{peso:.1f} MB" + (f" · {opciones.resumen()}" if opciones.resumen() else ""), salida)

        self._lanzar(lambda avance: guardar(paginas, ruta, avance, opciones), listo)

    def guardar(self) -> None:
        self._guardar(list(self.documento.paginas), todo=True)

    def guardar_seleccion(self) -> None:
        self._guardar([self.documento.paginas[f] for f in self.vista.filas()], todo=False)

    def dividir(self) -> None:
        if not len(self.documento):
            return
        filas = self.vista.filas()
        primera = self.documento.paginas[0].fuente.origen
        dialogo = DialogoDividir(self, len(self.documento), len(filas), primera.stem,
                                 carpeta_inicial("carpeta_guardar", primera.parent))
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        carpeta = Path(dialogo.carpeta.text().strip() or primera.parent)
        base = dialogo.base.text().strip() or "parte"
        paginas = ([self.documento.paginas[f] for f in filas] if dialogo.cuales.currentData() == "elegidas"
                   else list(self.documento.paginas))
        if dialogo.listo.isChecked():
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                inicios = inicios_de_documento([render.texto(p.fuente, p.indice) for p in paginas])
            finally:
                QApplication.restoreOverrideCursor()
            grupos = grupos_por_inicio(paginas, inicios)
            if len(inicios) == 0 or len(grupos) < 2:
                QMessageBox.information(self, APP_NAME, "No encontré en el texto de las hojas más de un «Página 1 de N», así que no "
                                        "sé dónde cortar.\n\nSi es un escaneo sin texto, divide cada tantas hojas.")
                return
        else:
            grupos = grupos_cada(paginas, dialogo.paso())
        existentes = [p for p in nombres_division(len(grupos), carpeta, base) if p.exists()]
        if existentes:
            respuesta = QMessageBox.question(self, APP_NAME, f"En esa carpeta ya hay {len(existentes)} archivos con esos nombres "
                                             f"(por ejemplo {existentes[0].name}).\n\n¿Reemplazarlos?")
            if respuesta != QMessageBox.StandardButton.Yes:
                return
        recordar_carpeta("carpeta_guardar", carpeta)
        opciones = self.opciones

        def listo(salidas: list[Path]) -> None:
            self.estado.emit(f"Dividido en {len(salidas)} PDF en {carpeta}")
            self._preguntar_abrir(f"{len(salidas)} PDF escritos en\n{carpeta}", carpeta)

        self._lanzar(lambda avance: dividir(paginas, carpeta, base, progreso=avance, opciones=opciones, grupos=grupos), listo)

    def _preguntar_abrir(self, texto: str, ruta: Path) -> None:
        caja = QMessageBox(QMessageBox.Icon.Information, APP_NAME, texto, parent=self)
        abrir = caja.addButton("Abrir", QMessageBox.ButtonRole.AcceptRole)
        carpeta = caja.addButton("Abrir carpeta", QMessageBox.ButtonRole.ActionRole) if ruta.is_file() else None
        caja.addButton("Cerrar", QMessageBox.ButtonRole.RejectRole)
        caja.exec()
        if caja.clickedButton() is abrir:
            abrir_en_sistema(ruta)
        elif carpeta is not None and caja.clickedButton() is carpeta:
            abrir_en_sistema(ruta.parent)

    # ------------------------------------------------------------------ cierre
    def cerrar(self) -> None:
        if self.tarea is not None and self.tarea.isRunning():
            self.tarea.wait(10000)
        self.hilo.parar()
        for fuente in self.documento.fuentes():
            fuente.cerrar()
        if self._temporal is not None:
            shutil.rmtree(self._temporal, ignore_errors=True)
