"""Ventana principal de Cirno (PySide6)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QSizePolicy, QVBoxLayout, QWidget,
)

from . import APP_KANA, APP_NAME, REPO_URL, __version__
from .convertir import Resultado, convertir, expandir, nombre_unido
from .theme import MUTED, QSS, sombra


def ruta_recurso(nombre: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for candidata in (base / "cirno" / "assets" / nombre, base / "assets" / nombre,
                      Path(__file__).resolve().parent / "assets" / nombre):
        if candidata.exists():
            return candidata
    return base / "assets" / nombre


class Trabajador(QThread):
    progreso = Signal(int, int, str)
    mensaje = Signal(str)
    terminado = Signal(object)

    def __init__(self, pdfs: list[Path], carpeta: Path | None, unir: bool, nombre: str | None):
        super().__init__()
        self.pdfs, self.carpeta, self.unir, self.nombre = pdfs, carpeta, unir, nombre

    def run(self) -> None:
        try:
            res = convertir(self.pdfs, self.carpeta, self.unir, self.nombre,
                            progreso=self.progreso.emit, log=self.mensaje.emit)
        except Exception as e:  # noqa: BLE001
            res = Resultado(errores=[str(e)])
        self.terminado.emit(res)


class ListaPdf(QListWidget):
    cambiada = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setMinimumHeight(150)

    def rutas(self) -> list[Path]:
        return [Path(self.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.count())]

    def agregar(self, rutas) -> int:
        actuales = {str(r) for r in self.rutas()}
        nuevas = 0
        for p in expandir(rutas):
            if str(p) in actuales:
                continue
            self.addItem(p.name)
            self.item(self.count() - 1).setData(Qt.ItemDataRole.UserRole, str(p))
            self.item(self.count() - 1).setToolTip(str(p))
            actuales.add(str(p))
            nuevas += 1
        if nuevas:
            self.cambiada.emit()
        return nuevas

    def quitar_seleccion(self) -> None:
        for item in self.selectedItems():
            self.takeItem(self.row(item))
        self.cambiada.emit()

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        rutas = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.agregar(rutas)
        e.acceptProposedAction()

    def paintEvent(self, e):  # noqa: N802
        super().paintEvent(e)
        if self.count() == 0:
            p = QPainter(self.viewport())
            p.setPen(QColor(MUTED))
            f = QFont(self.font())
            f.setPointSizeF(11)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter,
                       "Arrastra aquí los PDF\n(o carpetas con PDF)\n\no pulsa AÑADIR PDF")
            p.end()


class Ventana(QMainWindow):
    def __init__(self, pdfs: list[Path] | None = None, carpeta: str | None = None, unir: bool = False):
        super().__init__()
        self.ajustes = QSettings("Chidaruma", APP_NAME)
        self.trabajador: Trabajador | None = None
        self.ultima_salida: Path | None = None
        self.setWindowTitle(f"{APP_NAME} {APP_KANA}")
        self.setWindowIcon(QIcon(str(ruta_recurso("cirno.ico"))))
        self.setMinimumSize(720, 640)
        self._construir()
        self._cargar_ajustes()
        if carpeta:
            self.radio_carpeta.setChecked(True)
            self.campo_carpeta.setText(str(Path(carpeta)))
        if unir:
            self.check_unir.setChecked(True)
        if pdfs:
            self.lista.agregar(pdfs)
        self._actualizar_estado()

    # ------------------------------------------------------------------ construcción
    def _construir(self) -> None:
        raiz = QWidget()
        raiz.setObjectName("root")
        self.setCentralWidget(raiz)
        col = QVBoxLayout(raiz)
        col.setContentsMargins(24, 20, 24, 20)
        col.setSpacing(14)

        # Cabecera
        cab = QHBoxLayout()
        titulo = QLabel(APP_NAME.upper())
        titulo.setObjectName("titulo")
        kana = QLabel(APP_KANA)
        kana.setObjectName("kana")
        kicker = QLabel("ESTADOS DE CUENTA  ·  PDF → EXCEL")
        kicker.setObjectName("kicker")
        version = QLabel(f"v{__version__}")
        version.setObjectName("version")
        bloque = QVBoxLayout()
        bloque.setSpacing(0)
        fila_t = QHBoxLayout()
        fila_t.setSpacing(12)
        fila_t.addWidget(titulo)
        fila_t.addWidget(kana, 0, Qt.AlignmentFlag.AlignBottom)
        fila_t.addStretch()
        bloque.addLayout(fila_t)
        bloque.addWidget(kicker)
        cab.addLayout(bloque)
        cab.addStretch()
        cab.addWidget(version, 0, Qt.AlignmentFlag.AlignTop)
        col.addLayout(cab)

        # Panel de archivos
        panel_a, la = self._panel("01 · ARCHIVOS")
        self.lista = ListaPdf()
        self.lista.cambiada.connect(self._actualizar_estado)
        la.addWidget(self.lista)
        fila_b = QHBoxLayout()
        self.btn_agregar = self._boton("Añadir PDF…", self._elegir_pdf)
        self.btn_carpeta_pdf = self._boton("Añadir carpeta…", self._elegir_carpeta_pdf)
        self.btn_quitar = self._boton("Quitar", self.lista.quitar_seleccion)
        self.btn_limpiar = self._boton("Limpiar", self._limpiar)
        for b in (self.btn_agregar, self.btn_carpeta_pdf, self.btn_quitar, self.btn_limpiar):
            fila_b.addWidget(b)
        fila_b.addStretch()
        self.etiqueta_cuenta = QLabel("")
        self.etiqueta_cuenta.setObjectName("nota")
        fila_b.addWidget(self.etiqueta_cuenta)
        la.addLayout(fila_b)
        col.addWidget(panel_a)

        # Panel de salida
        panel_s, ls = self._panel("02 · SALIDA")
        self.radio_junto = QRadioButton("Junto a cada PDF")
        self.radio_carpeta = QRadioButton("En esta carpeta:")
        grupo = QButtonGroup(self)
        grupo.addButton(self.radio_junto)
        grupo.addButton(self.radio_carpeta)
        self.radio_junto.setChecked(True)
        self.campo_carpeta = QLineEdit()
        self.campo_carpeta.setReadOnly(True)
        self.campo_carpeta.setPlaceholderText("Elige una carpeta…")
        self.btn_elegir = self._boton("Elegir…", self._elegir_salida)
        fila_r = QHBoxLayout()
        fila_r.addWidget(self.radio_junto)
        fila_r.addSpacing(16)
        fila_r.addWidget(self.radio_carpeta)
        fila_r.addWidget(self.campo_carpeta, 1)
        fila_r.addWidget(self.btn_elegir)
        ls.addLayout(fila_r)
        self.check_unir = QCheckBox("Unir todo en un solo Excel con nombre:")
        self.campo_nombre = QLineEdit(nombre_unido())
        self.campo_nombre.setEnabled(False)
        fila_u = QHBoxLayout()
        fila_u.addWidget(self.check_unir)
        fila_u.addWidget(self.campo_nombre, 1)
        ls.addLayout(fila_u)
        nota = QLabel("Cada Excel lleva las hojas Resumen, Movimientos, Aplicaciones y Saldo final. "
                      "Si lo unes todo, cada fila indica de qué archivo y periodo viene.")
        nota.setObjectName("nota")
        nota.setWordWrap(True)
        ls.addWidget(nota)
        col.addWidget(panel_s)

        # Acción
        fila_c = QHBoxLayout()
        self.btn_convertir = QPushButton("CONVERTIR")
        self.btn_convertir.setObjectName("primario")
        self.btn_convertir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_convertir.clicked.connect(self._convertir)
        sombra(self.btn_convertir, 5)
        self.barra = QProgressBar()
        self.barra.setRange(0, 1)
        self.barra.setValue(0)
        self.barra.setFormat("%v / %m")
        fila_c.addWidget(self.btn_convertir)
        fila_c.addWidget(self.barra, 1)
        col.addLayout(fila_c)

        # Registro
        panel_l, ll = self._panel("03 · REGISTRO")
        self.registro = QPlainTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMinimumHeight(120)
        ll.addWidget(self.registro)
        fila_f = QHBoxLayout()
        self.btn_abrir = self._boton("Abrir carpeta de salida", self._abrir_salida)
        self.btn_abrir.setEnabled(False)
        fila_f.addWidget(self.btn_abrir)
        fila_f.addStretch()
        btn_acerca = QPushButton("Acerca de")
        btn_acerca.setObjectName("texto")
        btn_acerca.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_acerca.clicked.connect(self._acerca_de)
        fila_f.addWidget(btn_acerca)
        ll.addLayout(fila_f)
        col.addWidget(panel_l, 1)

        self.check_unir.toggled.connect(self.campo_nombre.setEnabled)
        self.radio_carpeta.toggled.connect(self._actualizar_estado)
        self.lista.itemSelectionChanged.connect(self._actualizar_estado)

    def _panel(self, titulo: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("panel")
        sombra(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        etiqueta = QLabel(titulo)
        etiqueta.setObjectName("seccion")
        lay.addWidget(etiqueta)
        return panel, lay

    def _boton(self, texto: str, accion) -> QPushButton:
        b = QPushButton(texto.upper())
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(accion)
        return b

    # ------------------------------------------------------------------ ajustes
    def _cargar_ajustes(self) -> None:
        carpeta = self.ajustes.value("carpeta_salida", "")
        if carpeta:
            self.campo_carpeta.setText(str(carpeta))
        if self.ajustes.value("usar_carpeta", False, type=bool) and carpeta:
            self.radio_carpeta.setChecked(True)
        self.check_unir.setChecked(self.ajustes.value("unir", False, type=bool))
        geometria = self.ajustes.value("geometria")
        if geometria:
            self.restoreGeometry(geometria)

    def closeEvent(self, e):  # noqa: N802
        self.ajustes.setValue("carpeta_salida", self.campo_carpeta.text())
        self.ajustes.setValue("usar_carpeta", self.radio_carpeta.isChecked())
        self.ajustes.setValue("unir", self.check_unir.isChecked())
        self.ajustes.setValue("geometria", self.saveGeometry())
        super().closeEvent(e)

    # ------------------------------------------------------------------ acciones
    def _elegir_pdf(self) -> None:
        inicio = self.ajustes.value("carpeta_pdf", str(Path.home() / "Downloads"))
        rutas, _ = QFileDialog.getOpenFileNames(self, "Elegir PDF", str(inicio), "PDF (*.pdf)")
        if rutas:
            self.ajustes.setValue("carpeta_pdf", str(Path(rutas[0]).parent))
            self.lista.agregar(rutas)

    def _elegir_carpeta_pdf(self) -> None:
        inicio = self.ajustes.value("carpeta_pdf", str(Path.home() / "Downloads"))
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta con PDF", str(inicio))
        if ruta:
            self.ajustes.setValue("carpeta_pdf", ruta)
            n = self.lista.agregar([ruta])
            if n == 0:
                self._log(f"⚠ No se encontraron PDF nuevos en {ruta}")

    def _limpiar(self) -> None:
        self.lista.clear()
        self.lista.cambiada.emit()

    def _elegir_salida(self) -> None:
        inicio = self.campo_carpeta.text() or str(Path.home())
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta de salida", inicio)
        if ruta:
            self.campo_carpeta.setText(ruta)
            self.radio_carpeta.setChecked(True)
        self._actualizar_estado()

    def _actualizar_estado(self) -> None:
        n = self.lista.count()
        ocupado = self.trabajador is not None and self.trabajador.isRunning()
        falta_carpeta = self.radio_carpeta.isChecked() and not self.campo_carpeta.text()
        self.btn_convertir.setEnabled(n > 0 and not ocupado and not falta_carpeta)
        self.btn_quitar.setEnabled(bool(self.lista.selectedItems()) and not ocupado)
        self.btn_limpiar.setEnabled(n > 0 and not ocupado)
        self.etiqueta_cuenta.setText(f"{n} PDF" if n != 1 else "1 PDF")

    def _log(self, texto: str) -> None:
        self.registro.appendPlainText(texto)

    def _convertir(self) -> None:
        pdfs = self.lista.rutas()
        if not pdfs:
            return
        carpeta = Path(self.campo_carpeta.text()) if self.radio_carpeta.isChecked() else None
        if carpeta and not carpeta.is_dir():
            QMessageBox.warning(self, APP_NAME, f"La carpeta de salida no existe:\n{carpeta}")
            return
        unir = self.check_unir.isChecked()
        nombre = self.campo_nombre.text().strip() or None
        self.registro.clear()
        self.barra.setRange(0, len(pdfs))
        self.barra.setValue(0)
        self.btn_abrir.setEnabled(False)
        self.ultima_salida = None
        self.trabajador = Trabajador(pdfs, carpeta, unir, nombre)
        self.trabajador.progreso.connect(self._progreso)
        self.trabajador.mensaje.connect(self._log)
        self.trabajador.terminado.connect(self._terminado)
        self.trabajador.start()
        self._actualizar_estado()

    def _progreso(self, hecho: int, total: int, nombre: str) -> None:
        self.barra.setRange(0, max(total, 1))
        self.barra.setValue(hecho)
        self.barra.setFormat(f"{nombre}  ({hecho}/{total})" if nombre else f"{hecho} / {total}")

    def _terminado(self, res: Resultado) -> None:
        if res.salidas:
            self.ultima_salida = res.salidas[-1].parent
            self.btn_abrir.setEnabled(True)
        if self.check_unir.isChecked():
            self.campo_nombre.setText(nombre_unido())
        resumen = f"Listo: {len(res.salidas)} Excel"
        if res.avisos:
            resumen += f", {len(res.avisos)} avisos"
        if res.errores:
            resumen += f", {len(res.errores)} errores"
        self._log("─" * 40)
        self._log(resumen)
        self._actualizar_estado()
        if res.errores:
            QMessageBox.warning(self, APP_NAME, "Hubo errores:\n\n" + "\n".join(res.errores))

    def _abrir_salida(self) -> None:
        if self.ultima_salida:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ultima_salida)))

    def _acerca_de(self) -> None:
        QMessageBox.about(self, f"Acerca de {APP_NAME}", f"""
<h2 style="margin:0">{APP_NAME} <span style="color:#2E7DE9">{APP_KANA}</span> <small>v{__version__}</small></h2>
<p>Convierte estados de cuenta en PDF a libros de Excel: resumen, movimientos,
aplicaciones de pagos y saldo final, con cifras cruzadas contra las CIFRAS CONTROL del PDF.</p>
<p><b>Créditos</b><br>
Diseño: estética Komi Store (papel y tinta).<br>
Lectura de PDF: <a href="https://github.com/jsvine/pdfplumber">pdfplumber</a> (MIT) sobre pdfminer.six.<br>
Excel: <a href="https://openpyxl.readthedocs.io/">openpyxl</a> (MIT).<br>
Interfaz: <a href="https://doc.qt.io/qtforpython-6/">Qt for Python / PySide6</a> (LGPL-3.0).<br>
Código fuente: <a href="{REPO_URL}">{REPO_URL}</a> (Apache 2.0).</p>
<p style="color:#6B7B8F;font-size:9pt">Touhou Project y sus personajes pertenecen a Team Shanghai Alice (ZUN);
obra de fans no oficial hecha según sus directrices para obras derivadas, sin afiliación ni respaldo.</p>
""")


def ejecutar(pdfs: list[Path] | None = None, carpeta: str | None = None, unir: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Chidaruma")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(QIcon(str(ruta_recurso("cirno.ico"))))
    ventana = Ventana(pdfs, carpeta, unir)
    ventana.show()
    return app.exec()
