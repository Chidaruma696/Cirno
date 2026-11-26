"""La ventana de Cirno: tres pestañas (organizar PDF, extraer datos, formato de Excel), el menú
y las actualizaciones. Aspecto nativo del sistema, sin hoja de estilos."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QThread, QTranslator, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QPushButton, QTabWidget

from .. import APP_KANA, APP_NAME, ORG, REPO_URL, __version__
from ..updater import Release, UpdateError, check, download, frozen, install
from .comun import ajustes, ruta_recurso
from .extraer import PestanaExtraer
from .formato import EXT_EXCEL, PestanaFormato
from .organizar import PestanaOrganizar


class BuscarVersion(QThread):
    """Pregunta a GitHub si hay una release más nueva; sin red no es un error para el usuario."""

    encontrada = Signal(object)
    ninguna = Signal()
    fallo = Signal(str)

    def run(self) -> None:
        try:
            release = check()
        except UpdateError as e:
            self.fallo.emit(str(e))
            return
        if release:
            self.encontrada.emit(release)
        else:
            self.ninguna.emit()


class BajarVersion(QThread):
    avance = Signal(int, int)
    lista = Signal(object)
    fallo = Signal(str)

    def __init__(self, release: Release) -> None:
        super().__init__()
        self.release = release

    def run(self) -> None:
        try:
            self.lista.emit(download(self.release, progress=self.avance.emit))
        except UpdateError as e:
            self.fallo.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.fallo.emit(f"{type(e).__name__}: {e}")


class Ventana(QMainWindow):
    def __init__(self, pdfs: list[Path] | None = None, excel: Path | None = None) -> None:
        super().__init__()
        self.release: Release | None = None
        self.buscador: BuscarVersion | None = None
        self.bajada: BajarVersion | None = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ruta_recurso("cirno.ico"))))
        self.setMinimumSize(900, 640)
        self.resize(1120, 760)

        self.organizar = PestanaOrganizar()
        self.extraer = PestanaExtraer()
        self.formato = PestanaFormato()
        self.pestanas = QTabWidget()
        self.pestanas.addTab(self.organizar, "Organizar y editar PDF")
        self.pestanas.addTab(self.extraer, "Extraer datos")
        self.pestanas.addTab(self.formato, "Excel en palabras")
        self.pestanas.setTabToolTip(0, "Unir varios PDF, ordenar las hojas, editarlas (texto, tapar, firmar, recortar), numerar, dividir")
        self.pestanas.setTabToolTip(1, "Sacar tablas y datos a Excel, imágenes y páginas a PNG o JPG")
        self.pestanas.setTabToolTip(2, "Pintar, ordenar, agrupar, quitar repetidos, sumar por grupos… dicho con tus palabras")
        self.setCentralWidget(self.pestanas)
        for pestana in (self.organizar, self.extraer, self.formato):
            pestana.estado.connect(lambda texto: self.statusBar().showMessage(texto, 15000))

        self.btn_actualizar = QPushButton("")
        self.btn_actualizar.setFlat(True)
        self.btn_actualizar.setVisible(False)
        self.btn_actualizar.clicked.connect(self._actualizar)
        self.statusBar().addPermanentWidget(self.btn_actualizar)
        self.statusBar().addPermanentWidget(QLabel(f"v{__version__} "))
        self._menus()
        self.setAcceptDrops(True)

        s = ajustes()
        geometria = s.value("geometria")
        if geometria:
            self.restoreGeometry(geometria)
        self.pestanas.setCurrentIndex(min(int(s.value("pestana", 0)), 2))
        if pdfs:
            self.extraer.anadir(pdfs)
            self.pestanas.setCurrentWidget(self.extraer)
        if excel:
            self.formato.cargar(excel)
            self.pestanas.setCurrentWidget(self.formato)
        if s.value("buscar_actualizaciones", True, type=bool):
            self._buscar_version(callado=True)

    # ------------------------------------------------------------------ menús
    def _menus(self) -> None:
        archivo = self.menuBar().addMenu("&Archivo")
        abrir = QAction("&Abrir…", self)
        abrir.setShortcut(QKeySequence("Ctrl+Shift+O"))
        abrir.triggered.connect(self._abrir)
        archivo.addAction(abrir)
        archivo.addSeparator()
        salir = QAction("&Salir", self)
        salir.setShortcut(QKeySequence("Ctrl+Q"))
        salir.triggered.connect(self.close)
        archivo.addAction(salir)

        ayuda = self.menuBar().addMenu("A&yuda")
        self.a_auto = QAction("Buscar actualizaciones al abrir", self, checkable=True)
        self.a_auto.setChecked(ajustes().value("buscar_actualizaciones", True, type=bool))
        self.a_auto.toggled.connect(lambda si: ajustes().setValue("buscar_actualizaciones", si))
        buscar = QAction("Buscar actualización ahora", self)
        buscar.triggered.connect(lambda: self._buscar_version(callado=False))
        web = QAction("Página del proyecto", self)
        web.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        acerca = QAction(f"Acerca de {APP_NAME}", self)
        acerca.triggered.connect(self._acerca_de)
        for a in (buscar, self.a_auto, None, web, acerca):
            ayuda.addSeparator() if a is None else ayuda.addAction(a)

    def _abrir(self) -> None:
        actual = self.pestanas.currentWidget()
        if actual is self.organizar:
            self.organizar.elegir_archivos()
        elif actual is self.extraer:
            self.extraer._elegir()
        else:
            self.formato._elegir()

    # ------------------------------------------------------------------ soltar archivos sobre la ventana
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        rutas = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        excels = [r for r in rutas if r.lower().endswith(EXT_EXCEL)]
        if excels:
            self.formato.cargar(Path(excels[0]))
            self.pestanas.setCurrentWidget(self.formato)
        elif self.pestanas.currentWidget() is self.extraer:
            self.extraer.anadir(rutas)
        else:
            self.pestanas.setCurrentWidget(self.organizar)
            self.organizar.anadir(rutas)
        e.acceptProposedAction()

    # ------------------------------------------------------------------ actualizaciones
    def _buscar_version(self, callado: bool) -> None:
        if self.buscador is not None and self.buscador.isRunning():
            return
        self.buscador = BuscarVersion()
        self.buscador.encontrada.connect(self._hay_version)
        if not callado:
            self.buscador.ninguna.connect(lambda: QMessageBox.information(self, APP_NAME, f"Ya tienes la última versión ({__version__})."))
            self.buscador.fallo.connect(lambda m: QMessageBox.information(self, APP_NAME, f"No pude consultar GitHub: {m}."))
        self.buscador.start()

    def _hay_version(self, release: Release) -> None:
        self.release = release
        self.btn_actualizar.setText(f"Hay una versión nueva ({release.version}): actualizar")
        self.btn_actualizar.setToolTip(release.page)
        self.btn_actualizar.setVisible(True)

    def _actualizar(self) -> None:
        if not self.release:
            return
        if not frozen():
            QDesktopServices.openUrl(QUrl(self.release.page))
            return
        if self.bajada is not None and self.bajada.isRunning():
            return
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText("Bajando…")
        self.bajada = BajarVersion(self.release)
        self.bajada.avance.connect(lambda hecho, total: self.btn_actualizar.setText(
            f"Bajando… {hecho * 100 // total} %" if total else f"Bajando… {hecho // (1024 * 1024)} MB"))
        self.bajada.lista.connect(self._version_lista)
        self.bajada.fallo.connect(self._version_fallida)
        self.bajada.start()

    def _version_lista(self, instalador: Path) -> None:
        self.btn_actualizar.setText(f"Hay una versión nueva ({self.release.version}): actualizar")
        self.btn_actualizar.setEnabled(True)
        respuesta = QMessageBox.question(
            self, APP_NAME,
            f"{APP_NAME} {self.release.version} está lista para instalarse.\n\n{APP_NAME} se cierra, se instala sola y "
            "vuelve a abrirse. Si tienes hojas sin guardar, guárdalas antes.\n\n¿Instalar ahora?")
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        self.organizar.documento.modificado = False
        install(instalador)
        QApplication.instance().quit()

    def _version_fallida(self, mensaje: str) -> None:
        self.btn_actualizar.setText(f"Hay una versión nueva ({self.release.version}): actualizar")
        self.btn_actualizar.setEnabled(True)
        QMessageBox.warning(self, APP_NAME, f"No se pudo bajar la actualización: {mensaje}.\n\nPuedes bajarla a mano:\n{self.release.page}")

    # ------------------------------------------------------------------ varios
    def _acerca_de(self) -> None:
        QMessageBox.about(self, f"Acerca de {APP_NAME}", f"""
<h2 style="margin:0">{APP_NAME} {APP_KANA} <small>v{__version__}</small></h2>
<p>Suite de PDF para la oficina: une varios PDF, ordena y edita sus hojas (escribir, corregir, tapar,
firmar, recortar, numerar), saca tablas y datos a Excel y las imágenes o las páginas a PNG o JPG, y le hace
a un Excel lo que le pidas con tus palabras. Sin inteligencia artificial y sin internet: todo son reglas que
se ejecutan en este equipo, y los originales nunca se modifican.</p>
<p><b>Créditos</b><br>
PDF: <a href="https://github.com/pikepdf/pikepdf">pikepdf</a> / qpdf (MPL-2.0, Apache-2.0),
<a href="https://github.com/pypdfium2-team/pypdfium2">pypdfium2</a> / PDFium (Apache-2.0, BSD-3),
<a href="https://github.com/jsvine/pdfplumber">pdfplumber</a> sobre pdfminer.six (MIT).<br>
Excel: <a href="https://openpyxl.readthedocs.io/">openpyxl</a> (MIT).
Imágenes: <a href="https://python-pillow.org/">Pillow</a> (MIT-CMU).<br>
Interfaz: <a href="https://doc.qt.io/qtforpython-6/">Qt for Python / PySide6</a> (LGPL-3.0).<br>
La idea de organizar las hojas en una rejilla viene de
<a href="https://github.com/pdfarranger/pdfarranger">PDF Arranger</a>; el código es propio.<br>
Código fuente: <a href="{REPO_URL}">{REPO_URL}</a> (Apache 2.0).</p>
<p><small>Touhou Project y sus personajes pertenecen a Team Shanghai Alice (ZUN); obra de fans no oficial
hecha según sus directrices para obras derivadas, sin afiliación ni respaldo.</small></p>
""")

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.organizar.hay_cambios():
            respuesta = QMessageBox.question(
                self, APP_NAME, "En «Organizar PDF» hay hojas que no has guardado.\n\n¿Salir de todos modos?")
            if respuesta != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        s = ajustes()
        s.setValue("geometria", self.saveGeometry())
        s.setValue("pestana", self.pestanas.currentIndex())
        self.extraer.cerrar()
        self.organizar.cerrar()
        super().closeEvent(e)


def ejecutar(pdfs: list[Path] | None = None, excel: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG)
    app.setWindowIcon(QIcon(str(ruta_recurso("cirno.ico"))))
    traductor = QTranslator(app)  # los botones de los diálogos de Qt (Sí, No, Cancelar), en español
    if traductor.load("qtbase_es", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(traductor)
    ventana = Ventana(pdfs, excel)
    ventana.show()
    return app.exec()
