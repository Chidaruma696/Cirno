"""Pestaña «Extraer»: se sueltan PDF, Cirno mira qué hay dentro de cada uno (un estado de
cuenta conocido, tablas, imágenes, texto) y lo enseña; se marca lo que se quiere y se saca a
Excel, PNG, JPG o texto."""

from __future__ import annotations

import queue
from pathlib import Path

import pikepdf
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSpinBox,
    QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import APP_NAME
from ..convertir import Opciones, Pedido, Resultado, expandir, exportar_pedidos, nombre_unido
from ..extraccion.analisis import Analisis, ClaveNecesaria, ImagenRef, analizar
from ..extraccion.tablas import Tabla
from ..pdf import render
from .comun import a_qimage, abrir_en_sistema, ajustes, carpeta_inicial, pedir_clave, recordar_carpeta

FILAS_VISTA = 200  # filas de una tabla que se enseñan en la vista previa
ROL = Qt.ItemDataRole.UserRole


class HiloAnalisis(QThread):
    """Analiza los PDF de uno en uno, en el orden en que se piden."""

    avance = Signal(str, int, int)  # ruta, página, total
    listo = Signal(str, object)  # ruta, Analisis

    def __init__(self) -> None:
        super().__init__()
        self._cola: queue.Queue = queue.Queue()
        self._parar = False

    def pedir(self, ruta: Path, clave: str | None = None) -> None:
        self._cola.put((ruta, clave))

    def parar(self) -> None:
        self._parar = True
        self._cola.put(None)
        self.wait(15000)

    def run(self) -> None:
        while not self._parar:
            pedido = self._cola.get()
            if pedido is None or self._parar:
                break
            ruta, clave = pedido
            try:
                a = analizar(ruta, clave, progreso=lambda i, n, r=ruta: self.avance.emit(str(r), i, n),
                             cancelar=lambda: self._parar)
            except ClaveNecesaria:
                a = Analisis(ruta=ruta, error="protegido con contraseña")
            except Exception as e:  # noqa: BLE001
                a = Analisis(ruta=ruta, error=f"{type(e).__name__}: {e}")
            self.listo.emit(str(ruta), a)


class HiloExportar(QThread):
    progreso = Signal(int, int, str)
    mensaje = Signal(str)
    terminado = Signal(object)

    def __init__(self, pedidos: list[Pedido], opciones: Opciones) -> None:
        super().__init__()
        self.pedidos, self.opciones = pedidos, opciones

    def run(self) -> None:
        try:
            res = exportar_pedidos(self.pedidos, self.opciones, self.progreso.emit, self.mensaje.emit)
        except Exception as e:  # noqa: BLE001
            res = Resultado(errores=[str(e)])
        self.terminado.emit(res)


class ArbolPdf(QTreeWidget):
    soltados = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setHeaderLabels(["Qué hay", "Detalle"])
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setStretchLastSection(False)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.setUniformRowHeights(True)

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        self.soltados.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        e.acceptProposedAction()

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        if self.topLevelItemCount() == 0:
            p = QPainter(self.viewport())
            p.setPen(self.palette().placeholderText().color())
            p.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter,
                       "Arrastra aquí los PDF\n(o carpetas con PDF)\n\nCirno mira qué tablas, datos e\nimágenes tiene cada uno")
            p.end()


class PestanaExtraer(QWidget):
    estado = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.analisis: dict[str, Analisis] = {}
        self.hilo = HiloAnalisis()
        self.hilo.avance.connect(self._avance_analisis)
        self.hilo.listo.connect(self._analizado)
        self.hilo.start()
        self.exportador: HiloExportar | None = None
        self.ultima_salida: Path | None = None
        self._vista_fuente: render.Fuente | None = None
        self._construir()
        self._cargar_ajustes()
        self._refrescar()

    # ------------------------------------------------------------------ construcción
    def _construir(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        botones = QHBoxLayout()
        self.btn_anadir = QPushButton("Añadir PDF…")
        self.btn_anadir.clicked.connect(self._elegir)
        self.btn_carpeta = QPushButton("Añadir carpeta…")
        self.btn_carpeta.clicked.connect(self._elegir_carpeta)
        self.btn_quitar = QPushButton("Quitar")
        self.btn_quitar.clicked.connect(self._quitar)
        self.btn_limpiar = QPushButton("Limpiar")
        self.btn_limpiar.clicked.connect(self._limpiar)
        for b in (self.btn_anadir, self.btn_carpeta, self.btn_quitar, self.btn_limpiar):
            botones.addWidget(b)
        botones.addStretch()
        self.cuenta = QLabel("")
        botones.addWidget(self.cuenta)
        col.addLayout(botones)

        partes = QSplitter(Qt.Orientation.Horizontal)
        self.arbol = ArbolPdf()
        self.arbol.soltados.connect(self.anadir)
        self.arbol.currentItemChanged.connect(self._mostrar)
        self.arbol.itemSelectionChanged.connect(self._refrescar)
        self.arbol.itemChanged.connect(lambda *_: self._refrescar())
        partes.addWidget(self.arbol)

        derecha = QWidget()
        cd = QVBoxLayout(derecha)
        cd.setContentsMargins(0, 0, 0, 0)
        self.titulo_vista = QLabel("Vista previa")
        self.titulo_vista.setWordWrap(True)
        cd.addWidget(self.titulo_vista)
        self.pila = QStackedWidget()
        self.vista_vacia = QLabel("Elige un elemento de la lista para verlo aquí antes de sacarlo.")
        self.vista_vacia.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vista_vacia.setWordWrap(True)
        self.vista_tabla = QTableWidget()
        self.vista_tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.vista_imagen = QLabel()
        self.vista_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zona = QScrollArea()
        zona.setWidget(self.vista_imagen)
        zona.setWidgetResizable(True)
        self.vista_texto = QPlainTextEdit()
        self.vista_texto.setReadOnly(True)
        for w in (self.vista_vacia, self.vista_tabla, zona, self.vista_texto):
            self.pila.addWidget(w)
        self._zona_imagen = zona
        cd.addWidget(self.pila, 1)
        partes.addWidget(derecha)
        partes.setStretchFactor(0, 4)
        partes.setStretchFactor(1, 5)
        col.addWidget(partes, 1)

        # Qué sacar
        caja = QGroupBox("Qué sacar")
        rejilla = QGridLayout(caja)
        self.chk_excel = QCheckBox("Tablas y datos → Excel")
        self.chk_excel.setChecked(True)
        self.chk_imagenes = QCheckBox("Imágenes incrustadas → PNG o JPG")
        self.chk_paginas = QCheckBox("Cada página como imagen → PNG o JPG")
        self.chk_texto = QCheckBox("Texto → .txt")
        self.formato = QComboBox()
        self.formato.addItem("PNG", "png")
        self.formato.addItem("JPG", "jpg")
        self.ppp = QSpinBox()
        self.ppp.setRange(50, 600)
        self.ppp.setSingleStep(50)
        self.ppp.setValue(150)
        self.ppp.setSuffix(" ppp")
        self.ppp.setToolTip("Resolución de las páginas como imagen: 150 para pantalla, 300 para imprimir")
        rejilla.addWidget(self.chk_excel, 0, 0)
        rejilla.addWidget(self.chk_texto, 1, 0)
        rejilla.addWidget(self.chk_imagenes, 0, 1)
        rejilla.addWidget(self.chk_paginas, 1, 1)
        rejilla.addWidget(QLabel("Formato de imagen:"), 0, 2, Qt.AlignmentFlag.AlignRight)
        rejilla.addWidget(self.formato, 0, 3)
        rejilla.addWidget(QLabel("Resolución de página:"), 1, 2, Qt.AlignmentFlag.AlignRight)
        rejilla.addWidget(self.ppp, 1, 3)
        self.chk_unir = QCheckBox("Unir los estados de cuenta en un solo Excel:")
        self.campo_nombre = QLineEdit(nombre_unido())
        self.campo_nombre.setEnabled(False)
        self.chk_unir.toggled.connect(self.campo_nombre.setEnabled)
        rejilla.addWidget(self.chk_unir, 2, 0, 1, 2)
        rejilla.addWidget(self.campo_nombre, 2, 2, 1, 2)
        rejilla.setColumnStretch(1, 1)
        col.addWidget(caja)

        # Dónde
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Guardar:"))
        self.radio_junto = QRadioButton("Junto a cada PDF")
        self.radio_carpeta = QRadioButton("En esta carpeta:")
        grupo = QButtonGroup(self)
        grupo.addButton(self.radio_junto)
        grupo.addButton(self.radio_carpeta)
        self.radio_junto.setChecked(True)
        self.campo_carpeta = QLineEdit()
        self.campo_carpeta.setReadOnly(True)
        self.campo_carpeta.setPlaceholderText("Elige una carpeta…")
        self.btn_elegir = QPushButton("Elegir…")
        self.btn_elegir.clicked.connect(self._elegir_salida)
        self.radio_carpeta.toggled.connect(self._refrescar)
        fila.addWidget(self.radio_junto)
        fila.addWidget(self.radio_carpeta)
        fila.addWidget(self.campo_carpeta, 1)
        fila.addWidget(self.btn_elegir)
        col.addLayout(fila)

        accion = QHBoxLayout()
        self.btn_extraer = QPushButton("Extraer")
        self.btn_extraer.setDefault(True)
        self.btn_extraer.setMinimumWidth(140)
        self.btn_extraer.clicked.connect(self._extraer)
        self.barra = QProgressBar()
        self.barra.setRange(0, 1)
        self.barra.setValue(0)
        self.barra.setTextVisible(True)
        self.barra.setFormat("")
        self.btn_abrir = QPushButton("Abrir carpeta de salida")
        self.btn_abrir.setEnabled(False)
        self.btn_abrir.clicked.connect(lambda: self.ultima_salida and abrir_en_sistema(self.ultima_salida))
        accion.addWidget(self.btn_extraer)
        accion.addWidget(self.barra, 1)
        accion.addWidget(self.btn_abrir)
        col.addLayout(accion)

        self.registro = QPlainTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMaximumHeight(110)
        self.registro.setPlaceholderText("Aquí aparece lo que se va escribiendo.")
        col.addWidget(self.registro)

    def _cargar_ajustes(self) -> None:
        s = ajustes()
        carpeta = s.value("carpeta_salida", "")
        if carpeta:
            self.campo_carpeta.setText(str(carpeta))
        if s.value("usar_carpeta", False, type=bool) and carpeta:
            self.radio_carpeta.setChecked(True)
        self.chk_unir.setChecked(s.value("unir", False, type=bool))
        self.formato.setCurrentIndex(max(0, self.formato.findData(s.value("formato_imagen", "png"))))
        self.ppp.setValue(int(s.value("ppp", 150)))

    def guardar_ajustes(self) -> None:
        s = ajustes()
        s.setValue("carpeta_salida", self.campo_carpeta.text())
        s.setValue("usar_carpeta", self.radio_carpeta.isChecked())
        s.setValue("unir", self.chk_unir.isChecked())
        s.setValue("formato_imagen", self.formato.currentData())
        s.setValue("ppp", self.ppp.value())

    # ------------------------------------------------------------------ archivos
    def _elegir(self) -> None:
        rutas, _ = QFileDialog.getOpenFileNames(self, "Elegir PDF", carpeta_inicial("carpeta_pdf", Path.home() / "Downloads"), "PDF (*.pdf)")
        if rutas:
            recordar_carpeta("carpeta_pdf", rutas[0])
            self.anadir(rutas)

    def _elegir_carpeta(self) -> None:
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta con PDF", carpeta_inicial("carpeta_pdf", Path.home() / "Downloads"))
        if ruta:
            recordar_carpeta("carpeta_pdf", ruta)
            if not self.anadir([ruta]):
                self.registro.appendPlainText(f"⚠ No se encontraron PDF nuevos en {ruta}")

    def _raiz(self, ruta: str) -> QTreeWidgetItem | None:
        for i in range(self.arbol.topLevelItemCount()):
            it = self.arbol.topLevelItem(i)
            if it.data(0, ROL) == ("pdf", ruta):
                return it
        return None

    def anadir(self, rutas) -> int:
        nuevos = 0
        for p in expandir(rutas):
            clave = str(p)
            if self._raiz(clave) is not None:
                continue
            it = QTreeWidgetItem([p.name, "en cola…"])
            it.setData(0, ROL, ("pdf", clave))
            it.setToolTip(0, clave)
            self.arbol.addTopLevelItem(it)
            self.hilo.pedir(p, self._clave_previa(p))
            nuevos += 1
        self._refrescar()
        return nuevos

    def _clave_previa(self, ruta: Path) -> str | None:
        """Si el PDF está protegido se pregunta antes de mandarlo a analizar (el hilo no puede preguntar)."""
        clave = None
        while True:
            try:
                pikepdf.open(str(ruta), password=clave or "").close()
                break
            except pikepdf.PasswordError:
                clave = pedir_clave(self, ruta.name, reintento=clave is not None)
                if clave is None:
                    return None
            except Exception:  # noqa: BLE001 - lo dirá el análisis
                break
        return clave

    def _quitar(self) -> None:
        raices = {it if it.parent() is None else it.parent() for it in self.arbol.selectedItems()}
        for it in raices:
            self.analisis.pop(it.data(0, ROL)[1], None)
            self.arbol.takeTopLevelItem(self.arbol.indexOfTopLevelItem(it))
        self._refrescar()

    def _limpiar(self) -> None:
        self.arbol.clear()
        self.analisis.clear()
        self.pila.setCurrentWidget(self.vista_vacia)
        self.titulo_vista.setText("Vista previa")
        self._refrescar()

    # ------------------------------------------------------------------ análisis
    def _avance_analisis(self, ruta: str, pagina: int, total: int) -> None:
        it = self._raiz(ruta)
        if it is not None:
            it.setText(1, f"mirando… página {pagina + 1} de {total}")

    def _analizado(self, ruta: str, a: Analisis) -> None:
        it = self._raiz(ruta)
        if it is None:
            return
        self.analisis[ruta] = a
        self.arbol.blockSignals(True)
        it.takeChildren()
        it.setText(1, a.resumen())
        if not a.error:
            if a.estado is not None:
                ec = a.estado
                hijo = QTreeWidgetItem([f"Estado de cuenta {ec.cuenta}".strip(),
                                        f"{ec.periodo_texto} · {len(ec.movimientos)} movimientos"])
                hijo.setData(0, ROL, ("estado", ruta))
                hijo.setCheckState(0, Qt.CheckState.Checked)
                it.addChild(hijo)
            else:
                for n, t in enumerate(a.tablas):
                    detalle = f"{t.donde} · {t.n_filas} filas × {t.n_columnas} columnas"
                    if t.comprobaciones:
                        bien = all(c for c, _ in t.comprobaciones)
                        detalle += " · totales comprobados ✓" if bien else " · ⚠ un total no cuadra"
                    nombre = f"Tabla {n + 1}" + (f" · {t.titulo[:48]}" if len(t.titulo.strip()) >= 3 else "")
                    hijo = QTreeWidgetItem([nombre, detalle])
                    hijo.setData(0, ROL, ("tabla", ruta, n))
                    hijo.setCheckState(0, Qt.CheckState.Checked)
                    hijo.setToolTip(1, "Encontrada por sus rayas" if t.origen == "rayas"
                                    else "Intuida por la alineación del texto: revísala en la vista previa")
                    it.addChild(hijo)
            if a.campos and a.estado is None:
                hijo = QTreeWidgetItem(["Datos sueltos", "1 dato" if len(a.campos) == 1 else f"{len(a.campos)} datos"])
                hijo.setData(0, ROL, ("datos", ruta))
                hijo.setCheckState(0, Qt.CheckState.Checked)
                hijo.setToolTip(1, "Lo que no va en tabla: «Cliente: …», folios, totales, RFC, CLABE, correos…")
                it.addChild(hijo)
            for n, im in enumerate(a.imagenes):
                hijo = QTreeWidgetItem([f"Imagen {im.numero}", f"{im.donde} · {im.ancho} × {im.alto} px"])
                hijo.setData(0, ROL, ("imagen", ruta, n))
                hijo.setCheckState(0, Qt.CheckState.Checked)
                it.addChild(hijo)
            if a.n_palabras:
                hijo = QTreeWidgetItem(["Texto", f"{a.n_palabras} palabras"])
                hijo.setData(0, ROL, ("texto", ruta))
                it.addChild(hijo)
            hijo = QTreeWidgetItem(["Páginas", "1 página" if a.n_paginas == 1 else f"{a.n_paginas} páginas"])
            hijo.setData(0, ROL, ("paginas", ruta))
            it.addChild(hijo)
            it.setExpanded(True)
        self.arbol.blockSignals(False)
        if self.arbol.currentItem() is it:
            self._mostrar(it)
        self._refrescar()

    # ------------------------------------------------------------------ vista previa
    def _mostrar(self, it: QTreeWidgetItem | None, _previo=None) -> None:
        dato = it.data(0, ROL) if it is not None else None
        a = self.analisis.get(dato[1]) if dato else None
        if not dato or a is None or a.error:
            self.titulo_vista.setText("Vista previa" if a is None else f"{a.ruta.name}: {a.resumen()}")
            self.pila.setCurrentWidget(self.vista_vacia)
            return
        tipo = dato[0]
        if tipo == "tabla":
            t: Tabla = a.tablas[dato[2]]
            modo = "encontrada por sus rayas" if t.origen == "rayas" else "intuida por la alineación del texto"
            pie = "".join(f"\n{'✓' if c else '⚠'} {detalle}" for c, detalle in t.comprobaciones)
            self.titulo_vista.setText(f"{a.ruta.name} · Tabla {dato[2] + 1} · {t.donde} · {t.n_filas} × {t.n_columnas} · {modo}{pie}")
            self._ver_filas(t.filas)
        elif tipo == "datos":
            self.titulo_vista.setText(f"{a.ruta.name} · Datos sueltos · irán a la hoja «Datos» del Excel")
            self._ver_filas([["Dato", "Valor", "Página"]] + [[c.nombre, c.valor, str(c.pagina)] for c in a.campos])
        elif tipo == "estado":
            ec = a.estado
            filas = [["Fecha", "Tipo", "Referencia", "Asignación", "Cargos", "Abonos", "Saldo final"]]
            for m in ec.movimientos:
                filas.append([f"{m.fecha:%d/%m/%Y}", m.tipo, m.referencia, m.asignacion,
                              *(f"{v:,.2f}" if v is not None else "" for v in (m.cargos, m.abonos, m.saldo_final))])
            avisos = f" · ⚠ {len(ec.avisos)} avisos" if ec.avisos else " · cifras de control cuadradas"
            self.titulo_vista.setText(f"{a.ruta.name} · {ec.razon_social} · {ec.periodo_texto}{avisos}")
            self._ver_filas(filas)
        elif tipo == "imagen":
            ref: ImagenRef = a.imagenes[dato[2]]
            self.titulo_vista.setText(f"{a.ruta.name} · Imagen {ref.numero} · {ref.donde} · {ref.ancho} × {ref.alto} px")
            try:
                with pikepdf.open(str(a.ruta), password=a.clave or "") as pdf:
                    imagen = pikepdf.PdfImage(pdf.get_object(ref.objgen)).as_pil_image()
                self._ver_imagen(QPixmap.fromImage(a_qimage(imagen)))
            except Exception:  # noqa: BLE001
                self.vista_vacia.setText("Esta imagen no se puede enseñar aquí (su codificación no es habitual).")
                self.pila.setCurrentWidget(self.vista_vacia)
        elif tipo == "texto":
            self.titulo_vista.setText(f"{a.ruta.name} · Texto · {a.n_palabras} palabras")
            self.vista_texto.setPlainText("\n\n".join(a.textos))
            self.pila.setCurrentWidget(self.vista_texto)
        else:  # el PDF o sus páginas: la primera página
            self.titulo_vista.setText(f"{a.ruta.name} · {a.resumen()}")
            try:
                fuente = render.abrir(a.ruta, clave=a.clave)
                try:
                    self._ver_imagen(QPixmap.fromImage(a_qimage(render.pintar(fuente, 0, lado_max=900))))
                finally:
                    fuente.cerrar()
            except Exception:  # noqa: BLE001
                self.pila.setCurrentWidget(self.vista_vacia)

    def _ver_filas(self, filas: list[list[str]]) -> None:
        cabeza, cuerpo = filas[0], filas[1:FILAS_VISTA + 1]
        self.vista_tabla.clear()
        self.vista_tabla.setColumnCount(len(cabeza))
        self.vista_tabla.setRowCount(len(cuerpo))
        self.vista_tabla.setHorizontalHeaderLabels([c or f"Columna {i + 1}" for i, c in enumerate(cabeza)])
        for i, fila in enumerate(cuerpo):
            for j, texto in enumerate(fila):
                celda = QTableWidgetItem(texto)
                if texto and texto[0] in "-$(0123456789" and texto[-1] in "0123456789-)%":
                    celda.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.vista_tabla.setItem(i, j, celda)
        self.vista_tabla.resizeColumnsToContents()
        self.pila.setCurrentWidget(self.vista_tabla)

    def _ver_imagen(self, mapa: QPixmap) -> None:
        hueco = self._zona_imagen.viewport().size()
        if mapa.width() > hueco.width() or mapa.height() > hueco.height():
            mapa = mapa.scaled(hueco, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.vista_imagen.setPixmap(mapa)
        self.pila.setCurrentWidget(self._zona_imagen)

    # ------------------------------------------------------------------ extraer
    def _refrescar(self) -> None:
        n = self.arbol.topLevelItemCount()
        ocupado = self.exportador is not None and self.exportador.isRunning()
        pendientes = n - len(self.analisis)
        falta_carpeta = self.radio_carpeta.isChecked() and not self.campo_carpeta.text()
        self.btn_extraer.setEnabled(bool(self.analisis) and not ocupado and not falta_carpeta and pendientes == 0)
        self.btn_quitar.setEnabled(bool(self.arbol.selectedItems()) and not ocupado)
        self.btn_limpiar.setEnabled(n > 0 and not ocupado)
        texto = "1 PDF" if n == 1 else f"{n} PDF"
        if pendientes > 0:
            texto += f" · mirando {pendientes}…"
        self.cuenta.setText(texto)

    def _elegir_salida(self) -> None:
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.campo_carpeta.text() or str(Path.home()))
        if ruta:
            self.campo_carpeta.setText(ruta)
            self.radio_carpeta.setChecked(True)
        self._refrescar()

    def _pedidos(self) -> list[Pedido]:
        pedidos = []
        for i in range(self.arbol.topLevelItemCount()):
            raiz = self.arbol.topLevelItem(i)
            a = self.analisis.get(raiz.data(0, ROL)[1])
            if a is None:
                continue
            tablas: list[Tabla] = []
            imagenes: list[ImagenRef] = []
            estado = datos = False
            for k in range(raiz.childCount()):
                hijo = raiz.child(k)
                dato = hijo.data(0, ROL)
                if hijo.checkState(0) != Qt.CheckState.Checked:
                    continue
                if dato[0] == "tabla":
                    tablas.append(a.tablas[dato[2]])
                elif dato[0] == "imagen":
                    imagenes.append(a.imagenes[dato[2]])
                elif dato[0] == "estado":
                    estado = True
                elif dato[0] == "datos":
                    datos = True
            # Sin nada marcado no hay Excel; si el PDF no tiene tablas, sí (va su texto).
            vale = estado if a.estado is not None else (bool(tablas) or datos or not (a.tablas or a.campos))
            con_excel = self.chk_excel.isChecked() and vale
            pedidos.append(Pedido(
                a, excel=con_excel, tablas=None if a.estado is not None else tablas, datos=datos,
                imagenes=imagenes if self.chk_imagenes.isChecked() else None,
                paginas=self.chk_paginas.isChecked(), texto=self.chk_texto.isChecked()))
        return pedidos

    def _extraer(self) -> None:
        if not any(c.isChecked() for c in (self.chk_excel, self.chk_imagenes, self.chk_paginas, self.chk_texto)):
            QMessageBox.information(self, APP_NAME, "Marca al menos una cosa en «Qué sacar».")
            return
        carpeta = Path(self.campo_carpeta.text()) if self.radio_carpeta.isChecked() else None
        if carpeta and not carpeta.is_dir():
            QMessageBox.warning(self, APP_NAME, f"La carpeta de salida no existe:\n{carpeta}")
            return
        pedidos = self._pedidos()
        if not pedidos:
            return
        opciones = Opciones(carpeta, self.chk_unir.isChecked(), self.campo_nombre.text().strip() or None,
                            self.formato.currentData(), self.ppp.value())
        self.registro.clear()
        self.barra.setRange(0, len(pedidos))
        self.barra.setValue(0)
        self.btn_abrir.setEnabled(False)
        self.exportador = HiloExportar(pedidos, opciones)
        self.exportador.progreso.connect(self._progreso)
        self.exportador.mensaje.connect(self.registro.appendPlainText)
        self.exportador.terminado.connect(self._terminado)
        self.exportador.start()
        self._refrescar()

    def _progreso(self, hecho: int, total: int, nombre: str) -> None:
        self.barra.setRange(0, max(total, 1))
        self.barra.setValue(hecho)
        self.barra.setFormat(f"{nombre}  ({hecho}/{total})" if nombre else f"{hecho} / {total}")

    def _terminado(self, res: Resultado) -> None:
        self.exportador.wait()
        if res.salidas:
            primera = res.salidas[0]
            carpeta = Path(self.campo_carpeta.text()) if self.radio_carpeta.isChecked() else None
            self.ultima_salida = carpeta or (primera.parent if primera.suffix.lower() in (".xlsx", ".txt") else primera.parent.parent)
            self.btn_abrir.setEnabled(True)
        if self.chk_unir.isChecked():
            self.campo_nombre.setText(nombre_unido())
        resumen = "Listo: 1 archivo" if len(res.salidas) == 1 else f"Listo: {len(res.salidas)} archivos"
        if res.avisos:
            resumen += f", {len(res.avisos)} avisos"
        if res.errores:
            resumen += f", {len(res.errores)} errores"
        self.registro.appendPlainText("─" * 40)
        self.registro.appendPlainText(resumen)
        self.estado.emit(resumen)
        self._refrescar()
        if res.errores:
            QMessageBox.warning(self, APP_NAME, "Hubo errores:\n\n" + "\n".join(res.errores))

    def cerrar(self) -> None:
        self.guardar_ajustes()
        self.hilo.parar()
        if self.exportador is not None and self.exportador.isRunning():
            self.exportador.wait(15000)
