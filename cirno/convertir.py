"""Orquesta la extracción de varios PDF: analiza cada uno y escribe lo que se haya pedido
(Excel, imágenes incrustadas, páginas como imagen, texto). La usan la ventana y la línea de
comandos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import excel
from .extraccion import exportar
from .extraccion.analisis import Analisis, ClaveNecesaria, ImagenRef, analizar
from .extraccion.tablas import Tabla

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


@dataclass
class Pedido:
    """Qué sacar de un PDF. `tablas` e `imagenes` en None significan «todas las que haya»."""

    analisis: Analisis
    excel: bool = True
    tablas: list[Tabla] | None = None
    imagenes: list[ImagenRef] | None = None  # None = no sacar; lista = esas
    datos: bool = True  # la hoja «Datos» con los datos sueltos
    paginas: bool = False
    texto: bool = False


@dataclass
class Opciones:
    carpeta: Path | None = None  # None = junto a cada PDF
    unir: bool = False  # los estados de cuenta, en un solo Excel
    nombre: str | None = None
    formato: str = "png"
    ppp: int = 150


def _n(cuantos: int, uno: str, varios: str) -> str:
    return f"1 {uno}" if cuantos == 1 else f"{cuantos} {varios}"


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


def exportar_pedidos(pedidos: list[Pedido], op: Opciones, progreso: Progreso | None = None,
                     log: Log | None = None) -> Resultado:
    log = log or (lambda _s: None)
    progreso = progreso or (lambda _i, _n, _s: None)
    res = Resultado()
    estados = []
    total = len(pedidos)

    for i, pedido in enumerate(pedidos):
        a = pedido.analisis
        pdf = a.ruta
        progreso(i, total, pdf.name)
        destino = Path(op.carpeta) if op.carpeta else pdf.parent
        if a.error:
            res.errores.append(f"{pdf.name}: {a.error}")
            log(f"✗ {pdf.name}: {a.error}")
            continue
        try:
            if pedido.excel:
                if a.estado is not None and pedido.tablas is None:
                    ec = a.estado
                    for aviso in ec.avisos:
                        res.avisos.append(f"{pdf.name}: {aviso}")
                        log(f"⚠ {pdf.name}: {aviso}")
                    log(f"✓ {pdf.name}: estado de cuenta {ec.cuenta or '?'}, periodo {ec.periodo_texto or '?'}, "
                        f"{len(ec.movimientos)} movimientos, {len(ec.saldo_final)} documentos en saldo final")
                    if op.unir:
                        estados.append(ec)
                    else:
                        salida = excel.guardar([ec], destino / f"{pdf.stem}.xlsx")
                        res.salidas.append(salida)
                        log(f"  → {salida}")
                else:
                    tablas = a.tablas if pedido.tablas is None else pedido.tablas
                    campos = a.campos if pedido.datos else []
                    for t in tablas:
                        for cuadra, detalle in t.comprobaciones:
                            if not cuadra:
                                res.avisos.append(f"{pdf.name}: no cuadra · {detalle}")
                            log(("✓ " if cuadra else "⚠ ") + f"{pdf.name}: " + ("cuadra" if cuadra else "NO CUADRA") + f" · {detalle}")
                    if tablas or campos:
                        filas = sum(t.n_filas for t in tablas)
                        extra = f", {_n(len(campos), 'dato suelto', 'datos sueltos')}" if campos else ""
                        log(f"✓ {pdf.name}: {_n(len(tablas), 'tabla', 'tablas')}, {filas} filas{extra}")
                    elif a.escaneado:
                        aviso = f"{pdf.name}: es un escaneo sin texto; no hay datos que pasar a Excel"
                        res.avisos.append(aviso)
                        log(f"⚠ {aviso}")
                    else:
                        aviso = f"{pdf.name}: no encontré tablas; va el texto renglón a renglón"
                        res.avisos.append(aviso)
                        log(f"⚠ {aviso}")
                    if tablas or campos or not a.escaneado:
                        salida = exportar.tablas_a_excel(tablas, destino / f"{pdf.stem}.xlsx", a.textos, campos)
                        res.salidas.append(salida)
                        log(f"  → {salida}")
            if pedido.imagenes:
                hechas, avisos = exportar.imagenes(a, pedido.imagenes, destino / f"{pdf.stem} - imágenes", op.formato)
                res.salidas += hechas
                for aviso in avisos:
                    res.avisos.append(f"{pdf.name}: {aviso}")
                    log(f"⚠ {pdf.name}: {aviso}")
                if hechas:
                    log(f"✓ {pdf.name}: {_n(len(hechas), 'imagen', 'imágenes')} → {hechas[0].parent}")
            if pedido.paginas:
                hechas = exportar.paginas(a, destino / f"{pdf.stem} - páginas", op.formato, op.ppp)
                res.salidas += hechas
                log(f"✓ {pdf.name}: {_n(len(hechas), 'página', 'páginas')} como imagen → {hechas[0].parent}")
            if pedido.texto:
                if a.n_palabras:
                    salida = exportar.texto(a, destino / f"{pdf.stem}.txt")
                    res.salidas.append(salida)
                    log(f"  → {salida}")
                else:
                    aviso = f"{pdf.name}: no tiene texto que sacar"
                    res.avisos.append(aviso)
                    log(f"⚠ {aviso}")
        except PermissionError:
            msg = f"{pdf.name}: no se pudo escribir (¿el archivo de salida está abierto en otro programa?)"
            res.errores.append(msg)
            log(f"✗ {msg}")
        except Exception as e:  # noqa: BLE001 - el fallo de un PDF no debe parar el resto
            res.errores.append(f"{pdf.name}: {e}")
            log(f"✗ {pdf.name}: {e}")

    if op.unir and estados:
        base = Path(op.carpeta) if op.carpeta else estados[0].archivo.parent
        nombre = (op.nombre or "").strip() or nombre_unido()
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


def convertir(pdfs, carpeta: str | Path | None = None, unir: bool = False, nombre: str | None = None,
              progreso: Progreso | None = None, log: Log | None = None, imagenes: bool = False,
              paginas: bool = False, texto: bool = False, formato: str = "png", ppp: int = 150,
              con_excel: bool = True) -> Resultado:
    """Analiza los PDF y saca de cada uno su Excel (y lo demás que se pida). Sin ventana."""
    log = log or (lambda _s: None)
    pedidos: list[Pedido] = []
    previos = Resultado()
    for pdf in [Path(p) for p in pdfs]:
        try:
            a = analizar(pdf)
        except ClaveNecesaria:
            msg = f"{pdf.name}: está protegido con contraseña"
            previos.errores.append(msg)
            log(f"✗ {msg}")
            continue
        pedidos.append(Pedido(a, excel=con_excel, imagenes=a.imagenes if imagenes else None, paginas=paginas, texto=texto))
    op = Opciones(Path(carpeta) if carpeta else None, unir, nombre, formato, ppp)
    res = exportar_pedidos(pedidos, op, progreso, log)
    res.errores = previos.errores + res.errores
    return res
