"""Lectura de estados de cuenta en PDF (formato Bachoco) a estructuras de Python.

El PDF no trae tablas "reales": solo texto colocado en coordenadas. Las columnas se
reconocen por la posición X de cada palabra (calibrada con varios estados de cuenta
del mismo formato) y las secciones por sus títulos ("RESUMEN", "Movimientos del
periodo", "Detalles de Saldo Final", "CIFRAS CONTROL"). No se depende de la fila de
encabezados porque en algunos PDF el extractor no la devuelve.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pdfplumber

# Ancho (pt) de los PDF con los que se calibraron las columnas. Si un PDF viene con
# otro tamaño de página, las fronteras se escalan en proporción.
PAGE_WIDTH_REF = 609.0
ROW_TOL = 2.5  # palabras a menos de esta distancia vertical van en la misma fila
FOOTER_X = 33.0  # los párrafos legales al pie empiezan en x≈28; las tablas, en x≥36

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
AMOUNT_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*\.\d{2}-?$|^-?\d+\.\d{2}-?$")

# (nombre de columna, frontera derecha en pt). None = hasta el borde de la página.
MOV_COLS = (
    ("fecha", 80), ("referencia", 147), ("asignacion", 215), ("cargos", 275),
    ("abonos", 335), ("saldo_final", 390), ("pago", 445), ("nota_credito", 506),
    ("documento", None),
)
SALDO_COLS = (
    ("fecha_doc", 93), ("vencimiento", 160), ("referencia", 226), ("asignacion", 298),
    ("cargo", 360), ("abono", 430), ("saldo", 495), ("descripcion", None),
)
RESUMEN_COLS = (("concepto", 375), ("dato", 470), ("importe", None))


class FormatoDesconocido(Exception):
    """El PDF no tiene la estructura de un estado de cuenta conocido."""


@dataclass
class Word:
    x0: float
    x1: float
    top: float
    text: str

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Aplicacion:
    pago: float | None
    nota_credito: float | None
    documento: str


@dataclass
class Movimiento:
    fecha: date
    referencia: str
    asignacion: str
    cargos: float | None
    abonos: float | None
    saldo_final: float | None
    aplicaciones: list[Aplicacion] = field(default_factory=list)

    @property
    def tipo(self) -> str:
        if not self.referencia and self.cargos is None and self.abonos is None:
            return "Saldo inicial"
        if self.abonos is not None:
            return "Abono"
        return "Cargo"


@dataclass
class ResumenLinea:
    concepto: str
    dato: date | int | str | None
    importe: float | None


@dataclass
class SaldoDetalle:
    fecha_doc: date | None
    vencimiento: date | None
    referencia: str
    asignacion: str
    cargo: float | None
    abono: float | None
    saldo: float | None
    descripcion: str


@dataclass
class EstadoCuenta:
    archivo: Path
    cuenta: str = ""
    razon_social: str = ""
    sociedad: str = ""
    periodo_inicio: date | None = None
    periodo_fin: date | None = None
    emision: datetime | None = None
    hojas: int | None = None
    resumen: list[ResumenLinea] = field(default_factory=list)
    movimientos: list[Movimiento] = field(default_factory=list)
    totales_movimientos: dict[str, float | None] = field(default_factory=dict)
    saldo_final: list[SaldoDetalle] = field(default_factory=list)
    totales_saldo: dict[str, float | None] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    @property
    def periodo_texto(self) -> str:
        if self.periodo_inicio and self.periodo_fin:
            return f"{self.periodo_inicio:%d/%m/%Y} al {self.periodo_fin:%d/%m/%Y}"
        return ""


# ----------------------------------------------------------------------------- utilidades

def parse_amount(text: str) -> float | None:
    text = text.strip()
    if not AMOUNT_RE.match(text):
        return None
    negativo = text.endswith("-") or text.startswith("-")
    valor = float(text.strip("-").replace(",", ""))
    return -valor if negativo else valor


def parse_date(text: str) -> date | None:
    text = text.strip()
    if not DATE_RE.match(text):
        return None
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _rows(page) -> list[list[Word]]:
    words = [Word(w["x0"], w["x1"], w["top"], w["text"]) for w in page.extract_words()]
    words.sort(key=lambda w: (w.top, w.x0))
    rows: list[list[Word]] = []
    actual: list[Word] = []
    ancla: float | None = None
    for w in words:
        if ancla is None or abs(w.top - ancla) <= ROW_TOL:
            if ancla is None:
                ancla = w.top
            actual.append(w)
        else:
            rows.append(sorted(actual, key=lambda w: w.x0))
            actual, ancla = [w], w.top
    if actual:
        rows.append(sorted(actual, key=lambda w: w.x0))
    return rows


def _split(row: list[Word], cols, scale: float) -> dict[str, str]:
    nombres = [n for n, _ in cols]
    fronteras = [b * scale for _, b in cols if b is not None]
    partes: dict[str, list[str]] = {n: [] for n in nombres}
    for w in row:
        partes[nombres[bisect_right(fronteras, w.center)]].append(w.text)
    return {n: " ".join(p) for n, p in partes.items()}


def _compacto(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _tiene_datos(row: list[Word]) -> bool:
    return any(DATE_RE.match(w.text) or AMOUNT_RE.match(w.text) for w in row)


# ----------------------------------------------------------------------------- metadatos

_META = (
    ("cuenta", re.compile(r"^Cuenta:\s*(\S+)")),
    ("razon_social", re.compile(r"^Raz\S*n\s*Social:\s*(.+?)(?:\s+Hoja\s+\d+\s+de\s+\d+)?$")),
    ("sociedad", re.compile(r"^Sociedad:\s*(.+?)(?:\s+Hoja\s+\d+\s+de\s+\d+)?$")),
)
_PERIODO = re.compile(r"^Periodo:\s*(\d{2}/\d{2}/\d{4})\s*al\s*(\d{2}/\d{2}/\d{4})")
_EMISION = re.compile(r"^F\.\s*Emisi\S*n:\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}:\d{2})")
_HOJAS = re.compile(r"Hoja\s+\d+\s+de\s+(\d+)")


def _leer_meta(ec: EstadoCuenta, text: str) -> None:
    for attr, rx in _META:
        if not getattr(ec, attr):
            m = rx.match(text)
            if m:
                setattr(ec, attr, m.group(1).strip())
    if ec.periodo_inicio is None:
        m = _PERIODO.match(text)
        if m:
            ec.periodo_inicio, ec.periodo_fin = parse_date(m.group(1)), parse_date(m.group(2))
    if ec.emision is None:
        m = _EMISION.match(text)
        if m:
            try:
                ec.emision = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M:%S")
            except ValueError:
                pass
    if ec.hojas is None:
        m = _HOJAS.search(text)
        if m:
            ec.hojas = int(m.group(1))


# ----------------------------------------------------------------------------- parser

def parse_pdf(path: str | Path) -> EstadoCuenta:
    path = Path(path)
    ec = EstadoCuenta(archivo=path)
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            scale = (page.width or PAGE_WIDTH_REF) / PAGE_WIDTH_REF
            _leer_pagina(ec, _rows(page), scale)
    if not ec.movimientos and not ec.resumen and not ec.saldo_final:
        raise FormatoDesconocido(f"{path.name}: no parece un estado de cuenta de este formato")
    _validar(ec)
    return ec


def _leer_pagina(ec: EstadoCuenta, rows: list[list[Word]], scale: float) -> None:
    estado: str | None = None
    for row in rows:
        text = " ".join(w.text for w in row)
        clave = _compacto(text)
        _leer_meta(ec, text)

        if clave == "resumen":
            estado = "resumen"
            continue
        if clave.startswith("movimientosdelperiodo"):
            estado = "mov"
            continue
        if clave.startswith("detallesdesaldofinal"):
            estado = "saldo"
            continue
        if clave.startswith("cifrascontrol"):
            if estado == "mov":
                c = _split(row, MOV_COLS, scale)
                ec.totales_movimientos = {k: parse_amount(c[k]) for k in ("cargos", "abonos", "pago", "nota_credito")}
            elif estado == "saldo":
                c = _split(row, SALDO_COLS, scale)
                ec.totales_saldo = {k: parse_amount(c[k]) for k in ("cargo", "abono")}
            estado = None
            continue
        if estado is None:
            continue
        if row[0].x0 < FOOTER_X * scale:  # párrafos legales al pie de página
            estado = None
            continue
        if not _tiene_datos(row):  # encabezados de columna
            continue

        if estado == "resumen":
            c = _split(row, RESUMEN_COLS, scale)
            dato: date | int | str | None = parse_date(c["dato"])
            if dato is None:
                dato = int(c["dato"]) if c["dato"].isdigit() else (c["dato"] or None)
            ec.resumen.append(ResumenLinea(c["concepto"].rstrip(":").strip(), dato, parse_amount(c["importe"])))
        elif estado == "mov":
            c = _split(row, MOV_COLS, scale)
            fecha = parse_date(c["fecha"])
            if fecha is not None:
                ec.movimientos.append(Movimiento(
                    fecha, c["referencia"], c["asignacion"],
                    parse_amount(c["cargos"]), parse_amount(c["abonos"]), parse_amount(c["saldo_final"]),
                ))
            else:
                ap = Aplicacion(parse_amount(c["pago"]), parse_amount(c["nota_credito"]), c["documento"])
                if ec.movimientos:
                    ec.movimientos[-1].aplicaciones.append(ap)
                else:
                    ec.avisos.append(f"Línea de aplicación sin movimiento previo: {text}")
        elif estado == "saldo":
            c = _split(row, SALDO_COLS, scale)
            ec.saldo_final.append(SaldoDetalle(
                parse_date(c["fecha_doc"]), parse_date(c["vencimiento"]), c["referencia"], c["asignacion"],
                parse_amount(c["cargo"]), parse_amount(c["abono"]), parse_amount(c["saldo"]), c["descripcion"],
            ))


def _validar(ec: EstadoCuenta) -> None:
    """Cruza las sumas de las tablas con las CIFRAS CONTROL del propio PDF."""
    def suma(valores) -> float:
        return round(sum(v for v in valores if v is not None), 2)

    comprobaciones = (
        ("cargos", suma(m.cargos for m in ec.movimientos), ec.totales_movimientos.get("cargos")),
        ("abonos", suma(m.abonos for m in ec.movimientos), ec.totales_movimientos.get("abonos")),
        ("pagos aplicados", suma(a.pago for m in ec.movimientos for a in m.aplicaciones), ec.totales_movimientos.get("pago")),
        ("cargos del saldo final", suma(d.cargo for d in ec.saldo_final), ec.totales_saldo.get("cargo")),
        ("abonos del saldo final", suma(d.abono for d in ec.saldo_final), ec.totales_saldo.get("abono")),
    )
    for nombre, calculado, control in comprobaciones:
        if control is None:
            continue
        if abs(calculado - control) > 0.005:
            ec.avisos.append(f"La suma de {nombre} ({calculado:,.2f}) no coincide con CIFRAS CONTROL ({control:,.2f})")


# ----------------------------------------------------------------------------- respaldo genérico

def extraer_generico(path: str | Path) -> list[tuple[str, list[list[str]]]]:
    """Para PDF que no son de este formato: devuelve (nombre de hoja, filas) por página,
    con las tablas que pdfplumber detecte o, si no hay, el texto línea a línea."""
    hojas: list[tuple[str, list[list[str]]]] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            tablas = page.extract_tables() or []
            if tablas:
                for j, tabla in enumerate(tablas, start=1):
                    filas = [[(c or "").replace("\n", " ").strip() for c in fila] for fila in tabla]
                    hojas.append((f"P{i} tabla {j}", filas))
            else:
                texto = page.extract_text() or ""
                hojas.append((f"P{i} texto", [[linea] for linea in texto.splitlines() if linea.strip()]))
    return hojas
