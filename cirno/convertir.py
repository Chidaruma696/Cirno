"""Orquesta la conversión PDF → Excel. La usan tanto la ventana como la línea de comandos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import excel
from .parser import EstadoCuenta, FormatoDesconocido, extraer_generico, parse_pdf

Progreso = Callable[[int, int, str], None]
Log = Callable[[str], None]


@dataclass
class Resultado:
    salidas: list[Path] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores


def nombre_unido() -> str:
    return f"Cirno-{datetime.now():%Y%m%d-%H%M}.xlsx"


def expandir(rutas) -> list[Path]:
    """Acepta archivos y carpetas; de las carpetas toma los *.pdf. Sin duplicados, en orden."""
    vistos: dict[Path, None] = {}
    for r in rutas:
        p = Path(r)
        if p.is_dir():
            for pdf in sorted(p.glob("*.pdf")):
                vistos.setdefault(pdf.resolve(), None)
        elif p.suffix.lower() == ".pdf" and p.exists():
            vistos.setdefault(p.resolve(), None)
    return list(vistos)


def convertir(
    pdfs,
    carpeta: str | Path | None = None,
    unir: bool = False,
    nombre: str | None = None,
    progreso: Progreso | None = None,
    log: Log | None = None,
) -> Resultado:
    log = log or (lambda _s: None)
    progreso = progreso or (lambda _i, _n, _s: None)
    pdfs = [Path(p) for p in pdfs]
    res = Resultado()
    estados: list[EstadoCuenta] = []
    total = len(pdfs)

    for i, pdf in enumerate(pdfs):
        progreso(i, total, pdf.name)
        destino = Path(carpeta) if carpeta else pdf.parent
        try:
            try:
                ec = parse_pdf(pdf)
            except FormatoDesconocido:
                aviso = f"{pdf.name}: no es un estado de cuenta conocido; se vuelca el contenido tal cual"
                res.avisos.append(aviso)
                log(f"⚠ {aviso}")
                salida = excel.guardar_generico(extraer_generico(pdf), destino / f"{pdf.stem}.xlsx")
                res.salidas.append(salida)
                log(f"  → {salida}")
                continue
            for a in ec.avisos:
                res.avisos.append(f"{pdf.name}: {a}")
                log(f"⚠ {pdf.name}: {a}")
            log(f"✓ {pdf.name}: cuenta {ec.cuenta or '?'}, periodo {ec.periodo_texto or '?'}, "
                f"{len(ec.movimientos)} movimientos, {len(ec.saldo_final)} documentos en saldo final")
            if unir:
                estados.append(ec)
            else:
                salida = excel.guardar([ec], destino / f"{pdf.stem}.xlsx")
                res.salidas.append(salida)
                log(f"  → {salida}")
        except PermissionError:
            msg = f"{pdf.name}: no se pudo escribir el Excel (¿está abierto en Excel?)"
            res.errores.append(msg)
            log(f"✗ {msg}")
        except Exception as e:  # noqa: BLE001 - cualquier fallo de un PDF no debe parar el resto
            res.errores.append(f"{pdf.name}: {e}")
            log(f"✗ {pdf.name}: {e}")

    if unir and estados:
        base = Path(carpeta) if carpeta else pdfs[0].parent
        nombre = (nombre or "").strip() or nombre_unido()
        if not nombre.lower().endswith(".xlsx"):
            nombre += ".xlsx"
        try:
            salida = excel.guardar(estados, base / nombre, combinado=True)
            res.salidas.append(salida)
            log(f"→ {salida} ({len(estados)} estados de cuenta unidos)")
        except PermissionError:
            msg = f"{nombre}: no se pudo escribir el Excel (¿está abierto en Excel?)"
            res.errores.append(msg)
            log(f"✗ {msg}")

    progreso(total, total, "")
    return res
