"""Pestaña «Excel en palabras»: se elige un libro, se dice qué se quiere (pintar, ordenar,
agrupar, quitar repetidos, sumar por grupos…), se revisa lo que Cirno entendió y se aplica
en una copia. «Ideas» enseña el recetario y deja buscar en él."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import APP_NAME
from ..formato import recetas
from ..formato.recetas import Accion, Plan, RecetaError
from ..formato.rules import Rule, RuleError, plan_to_dict, rules_from_plan
from ..formato.workbook import SheetInfo, inspect, output_path, preview, sheet_names, value_index
from .comun import abrir_en_sistema, carpeta_inicial, recordar_carpeta

EXT_EXCEL = (".xlsx", ".xlsm")
QUE_HACE = {"ordenar": "ordena", "agrupar": "agrupa", "quitar_repetidos": "quita filas", "dejar": "quita filas", "quitar_filas": "quita filas",
            "columna": "fórmulas", "texto": "cambia texto", "resumen": "hoja nueva", "totales": "fórmulas", "formato_numero": "formato",
            "filtros": "filtros"}


class CampoExcel(QLineEdit):
    """Campo de solo lectura que acepta un .xlsx soltado encima."""

    soltado = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Arrastra aquí un Excel (.xlsx) o pulsa «Elegir…»")

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        for u in e.mimeData().urls():
            if u.isLocalFile() and u.toLocalFile().lower().endswith(EXT_EXCEL):
                self.soltado.emit(u.toLocalFile())
                break
        e.acceptProposedAction()


class DialogoIdeas(QDialog):
    """El recetario a la vista: se escribe una palabra y quedan las recetas que tienen que ver."""

    def __init__(self, padre: QWidget, columnas: list[str]) -> None:
        super().__init__(padre)
        self.setWindowTitle("Ideas: lo que Cirno sabe hacerle a un Excel")
        self.resize(720, 520)
        self.elegida: str | None = None
        col = QVBoxLayout(self)
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Escribe lo que quieres hacer: «repetidos», «sumar por cliente», «ordenar»…")
        self.buscar.setClearButtonEnabled(True)
        self.buscar.textChanged.connect(self._filtrar)
        col.addWidget(self.buscar)
        self.lista = QListWidget()
        self.lista.setWordWrap(True)
        self.lista.setSpacing(2)
        self.lista.itemDoubleClicked.connect(self._usar)
        col.addWidget(self.lista, 1)
        pie = QLabel("Doble clic en una receta pone su ejemplo en la orden; cámbiale los nombres por los de tus columnas"
                     + (f" ({', '.join(columnas[:8])}{'…' if len(columnas) > 8 else ''})." if columnas else ".")
                     + " Para pintar basta decir el color: «rojo donde Estado sea PENDIENTE», «en negrita los Importes mayores de 50 mil».")
        pie.setWordWrap(True)
        pie.setEnabled(False)
        col.addWidget(pie)
        fila = QHBoxLayout()
        fila.addStretch()
        usar = QPushButton("Usar el ejemplo")
        usar.setDefault(True)
        usar.clicked.connect(lambda: self._usar(self.lista.currentItem()))
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.reject)
        fila.addWidget(usar)
        fila.addWidget(cerrar)
        col.addLayout(fila)
        self._filtrar("")

    def _filtrar(self, texto: str) -> None:
        self.lista.clear()
        for r in recetas.buscar_recetas(texto):
            it = QListWidgetItem(f"{r.titulo}\n{r.descripcion}\nEjemplos:  " + "  ·  ".join(f"«{e}»" for e in r.ejemplos))
            it.setData(Qt.ItemDataRole.UserRole, r.ejemplos[0])
            self.lista.addItem(it)
        if not self.lista.count():
            it = QListWidgetItem("No tengo ninguna receta que suene a eso. Prueba con otra palabra, o bórralo para verlas todas.")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lista.addItem(it)
        else:
            self.lista.setCurrentRow(0)

    def _usar(self, it: QListWidgetItem | None) -> None:
        if it is not None and it.data(Qt.ItemDataRole.UserRole):
            self.elegida = it.data(Qt.ItemDataRole.UserRole)
            self.accept()


class PestanaFormato(QWidget):
    estado = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.origen: Path | None = None
        self.info: SheetInfo | None = None
        self.plan = Plan()
        self.ultima_salida: Path | None = None
        self.setAcceptDrops(True)
        self._construir()
        self._refrescar()

    # ------------------------------------------------------------------ construcción
    def _construir(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        caja, lay = self._caja("1 · Archivo")
        fila = QHBoxLayout()
        self.campo = CampoExcel()
        self.campo.soltado.connect(lambda p: self.cargar(Path(p)))
        self.btn_elegir = QPushButton("Elegir…")
        self.btn_elegir.clicked.connect(self._elegir)
        fila.addWidget(self.campo, 1)
        fila.addWidget(self.btn_elegir)
        lay.addLayout(fila)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Hoja:"))
        self.hoja = QComboBox()
        self.hoja.setMinimumWidth(180)
        self.hoja.currentTextChanged.connect(self._hoja_cambiada)
        fila.addWidget(self.hoja)
        self.forma = QLabel("")
        self.forma.setWordWrap(True)
        fila.addWidget(self.forma, 1)
        lay.addLayout(fila)
        col.addWidget(caja)

        caja, lay = self._caja("2 · Qué quieres hacer")
        self.orden = QPlainTextEdit()
        self.orden.setPlaceholderText(
            "Dilo con tus palabras, varias cosas a la vez si quieres. Ejemplo: busca los valores iguales de Cliente, agrúpalos y "
            "pinta de rojo los que sean PENDIENTE; suma el Importe por Cliente y pon filtros.")
        self.orden.setMaximumHeight(84)
        lay.addWidget(self.orden)
        fila = QHBoxLayout()
        self.btn_entender = QPushButton("Entender")
        self.btn_entender.setMinimumWidth(120)
        self.btn_entender.clicked.connect(self._entender)
        fila.addWidget(self.btn_entender)
        self.btn_ideas = QPushButton("Ideas…")
        self.btn_ideas.setToolTip("Ver y buscar todo lo que se le puede pedir")
        self.btn_ideas.clicked.connect(self._ideas)
        fila.addWidget(self.btn_ideas)
        self.aviso = QLabel("")
        self.aviso.setWordWrap(True)
        fila.addWidget(self.aviso, 1)
        self.btn_cargar = QPushButton("Cargar reglas…")
        self.btn_cargar.clicked.connect(self._cargar_reglas)
        self.btn_guardar = QPushButton("Guardar reglas…")
        self.btn_guardar.setToolTip("Guarda las reglas de pintar para aplicarlas otro mes a la misma hoja")
        self.btn_guardar.clicked.connect(self._guardar_reglas)
        fila.addWidget(self.btn_cargar)
        fila.addWidget(self.btn_guardar)
        lay.addLayout(fila)
        col.addWidget(caja)

        caja, lay = self._caja("3 · Lo que entendí")
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["", "Paso", "Columna", "Hace", "Alcanza"])
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i in (0, 2, 3, 4):
            self.tabla.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setMinimumHeight(140)
        lay.addWidget(self.tabla, 1)
        self.etiqueta_notas = QLabel("")
        self.etiqueta_notas.setWordWrap(True)
        lay.addWidget(self.etiqueta_notas)
        col.addWidget(caja, 1)

        fila = QHBoxLayout()
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_aplicar.setMinimumWidth(140)
        self.btn_aplicar.setDefault(True)
        self.btn_aplicar.clicked.connect(self._aplicar)
        fila.addWidget(self.btn_aplicar)
        self.destino = QLineEdit()
        self.destino.setPlaceholderText("Se guarda como «<nombre> - Cirno.xlsx» junto al original")
        fila.addWidget(self.destino, 1)
        self.btn_destino = QPushButton("Destino…")
        self.btn_destino.clicked.connect(self._elegir_destino)
        fila.addWidget(self.btn_destino)
        self.btn_abrir = QPushButton("Abrir el resultado")
        self.btn_abrir.setEnabled(False)
        self.btn_abrir.clicked.connect(lambda: self.ultima_salida and abrir_en_sistema(self.ultima_salida))
        fila.addWidget(self.btn_abrir)
        col.addLayout(fila)

        pista = QLabel("El original no se toca: todo se hace en una copia. Lo pintado es formato condicional de Excel y los totales y "
                       "resúmenes son fórmulas, así que siguen vivos si cambian los datos. Se entiende aquí mismo, en español, sin internet.")
        pista.setWordWrap(True)
        pista.setEnabled(False)
        col.addWidget(pista)

    @staticmethod
    def _caja(titulo: str) -> tuple[QGroupBox, QVBoxLayout]:
        caja = QGroupBox(titulo)
        return caja, QVBoxLayout(caja)

    # ------------------------------------------------------------------ soltar en cualquier parte
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if any(u.isLocalFile() and u.toLocalFile().lower().endswith(EXT_EXCEL) for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        for u in e.mimeData().urls():
            if u.isLocalFile() and u.toLocalFile().lower().endswith(EXT_EXCEL):
                self.cargar(Path(u.toLocalFile()))
                break
        e.acceptProposedAction()

    # ------------------------------------------------------------------ archivo
    def _elegir(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir Excel", carpeta_inicial("carpeta_excel"), "Excel (*.xlsx *.xlsm)")
        if ruta:
            recordar_carpeta("carpeta_excel", ruta)
            self.cargar(Path(ruta))

    def cargar(self, ruta: Path, hoja: str | None = None) -> None:
        try:
            nombres = sheet_names(ruta)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, f"No pude abrir el archivo:\n{e}")
            return
        self.origen = ruta
        self.campo.setText(str(ruta))
        self.hoja.blockSignals(True)
        self.hoja.clear()
        self.hoja.addItems(nombres)
        if hoja and hoja in nombres:
            self.hoja.setCurrentText(hoja)
        self.hoja.blockSignals(False)
        self.destino.setText(str(output_path(ruta)))
        self._hoja_cambiada()

    def _hoja_cambiada(self) -> None:
        if not self.origen or not self.hoja.currentText():
            return
        try:
            self.info = inspect(self.origen, self.hoja.currentText())
        except Exception as e:  # noqa: BLE001
            self.info = None
            self.forma.setText(f"✗ {e}")
            self._refrescar()
            return
        filas = self.info.last_row - self.info.first_row + 1
        columnas = ", ".join(c.header for c in self.info.columns)
        self.forma.setText(f"{filas} filas · {len(self.info.columns)} columnas: {columnas}")
        if self.plan.pasos:
            self._vista_previa()
        self._refrescar()

    # ------------------------------------------------------------------ entender
    def _ideas(self) -> None:
        d = DialogoIdeas(self, [c.header for c in self.info.columns] if self.info else [])
        if d.exec() == QDialog.DialogCode.Accepted and d.elegida:
            actual = self.orden.toPlainText().strip()
            self.orden.setPlainText(f"{actual}; {d.elegida}" if actual else d.elegida)
            self.orden.setFocus()

    def _entender(self) -> None:
        if not self.info:
            return
        texto = self.orden.toPlainText().strip()
        if not texto:
            return
        self.plan = recetas.entender(texto, self.info, value_index(self.origen, self.info))
        extra = f"  ⚠ {len(self.plan.notas)} sin entender" if self.plan.notas else ""
        self.aviso.setText(("1 paso" if len(self.plan.pasos) == 1 else f"{len(self.plan.pasos)} pasos") + extra)
        self._vista_previa()
        self._refrescar()

    def _vista_previa(self) -> None:
        self.tabla.setRowCount(0)
        notas = "\n".join(self.plan.notas)
        if not (self.info and self.plan.pasos):
            self.etiqueta_notas.setText(notas)
            return
        alcances: dict[int, str] = {}
        try:
            for pv in preview(self.origen, self.info, self.plan.reglas):
                alcances[id(pv.rule)] = f"{pv.cells} {'filas' if pv.rule.scope == 'row' else 'celdas'}"
            recetas.prever(self.origen, self.info, self.plan)
        except RuleError as e:
            notas = f"✗ {e}\n{notas}".strip()
        self.tabla.setRowCount(len(self.plan.pasos))
        for i, paso in enumerate(self.plan.pasos):
            casilla = QCheckBox()
            casilla.setChecked(paso.enabled)
            casilla.toggled.connect(lambda si, p=paso: setattr(p, "enabled", si))
            soporte = QWidget()
            hl = QHBoxLayout(soporte)
            hl.setContentsMargins(6, 0, 6, 0)
            hl.addWidget(casilla, 0, Qt.AlignmentFlag.AlignCenter)
            self.tabla.setCellWidget(i, 0, soporte)
            if isinstance(paso, Rule):
                self.tabla.setItem(i, 1, QTableWidgetItem(paso.description or paso.column))
                self.tabla.setItem(i, 2, QTableWidgetItem(paso.column))
                muestra = QTableWidgetItem("  pinta la " + ("fila" if paso.scope == "row" else "celda") + "  ")
                if paso.style.fill:
                    muestra.setBackground(QColor("#" + paso.style.fill))
                    muestra.setForeground(QColor("#" + (paso.style.font_color or "202020")))
                elif paso.style.font_color:
                    muestra.setForeground(QColor("#" + paso.style.font_color))
                letra = muestra.font()
                letra.setBold(bool(paso.style.bold))
                letra.setItalic(bool(paso.style.italic))
                letra.setStrikeOut(bool(paso.style.strike))
                muestra.setFont(letra)
                self.tabla.setItem(i, 3, muestra)
                alcance = alcances.get(id(paso), "")
            else:
                self.tabla.setItem(i, 1, QTableWidgetItem(paso.descripcion))
                self.tabla.setItem(i, 2, QTableWidgetItem(paso.columna or "—"))
                self.tabla.setItem(i, 3, QTableWidgetItem("  " + QUE_HACE.get(paso.receta, "") + "  "))
                alcance = paso.alcance
            cuenta = QTableWidgetItem(alcance)
            cuenta.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if alcance.startswith("0 "):
                cuenta.setForeground(self.palette().placeholderText())
            self.tabla.setItem(i, 4, cuenta)
        self.etiqueta_notas.setText(notas)

    def _cargar_reglas(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Cargar reglas", carpeta_inicial("carpeta_excel"), "Reglas (*.json)")
        if not ruta:
            return
        try:
            datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
            reglas, notas, errores = rules_from_plan(datos)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, f"No pude leer las reglas:\n{e}")
            return
        self.plan = Plan(pasos=list(reglas), notas=[notas] if notas else [])
        self.aviso.setText(f"{len(reglas)} reglas de {Path(ruta).name}" + (f"  ⚠ {len(errores)} descartadas" if errores else ""))
        self._vista_previa()
        self._refrescar()

    def _guardar_reglas(self) -> None:
        if not self.plan.reglas:
            return
        inicio = str(self.origen.with_suffix(".reglas.json")) if self.origen else ""
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar reglas", inicio, "Reglas (*.json)")
        if ruta:
            Path(ruta).write_text(json.dumps(plan_to_dict(self.plan.reglas, "\n".join(self.plan.notas)), ensure_ascii=False, indent=2),
                                  encoding="utf-8")

    # ------------------------------------------------------------------ aplicar
    def _elegir_destino(self) -> None:
        inicio = self.destino.text() or (str(output_path(self.origen)) if self.origen else "")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar como", inicio, "Excel (*.xlsx)")
        if ruta:
            self.destino.setText(ruta)

    def _aplicar(self) -> None:
        if not (self.origen and self.info and self.plan.pasos):
            return
        destino = Path(self.destino.text()) if self.destino.text().strip() else output_path(self.origen)
        try:
            salida = recetas.aplicar(self.origen, self.info.name, self.plan.pasos, destino)
        except PermissionError:
            QMessageBox.warning(self, APP_NAME, f"No se pudo guardar «{destino.name}» (¿está abierto en Excel?).")
            return
        except (RecetaError, RuleError, OSError) as e:
            QMessageBox.warning(self, APP_NAME, f"No se pudo hacer:\n\n{e}")
            return
        self.ultima_salida = salida
        self.btn_abrir.setEnabled(True)
        n = sum(1 for p in self.plan.pasos if p.enabled)
        self.aviso.setText(f"✓ {'1 paso hecho' if n == 1 else f'{n} pasos hechos'} en {salida.name}")
        self.estado.emit(f"Excel listo: {salida}")

    def _refrescar(self) -> None:
        self.btn_entender.setEnabled(bool(self.info))
        self.btn_aplicar.setEnabled(bool(self.info and self.plan.pasos))
        self.btn_guardar.setEnabled(bool(self.plan.reglas))
        self.btn_cargar.setEnabled(bool(self.info))
