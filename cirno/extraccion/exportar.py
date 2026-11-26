"""Sacar del PDF lo que el análisis encontró: tablas y datos a Excel, imágenes incrustadas y
páginas enteras a PNG o JPG, y el texto a un .txt."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pikepdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image

from .. import excel
from ..pdf import render
from .analisis import Analisis, ImagenRef
from .tablas import Tabla
from .valores import tipar, tipar_columna

Progreso = Callable[[int, int], None]

FORMATOS_IMAGEN = {"png": ("PNG", ".png"), "jpg": ("JPEG", ".jpg")}
CALIDAD_JPG = 90

_CAB_FUENTE = Font(bold=True, color="FFFFFF")
_CAB_RELLENO = PatternFill("solid", fgColor=excel.INK)
_PROHIBIDOS_HOJA = re.compile(r"[\\/?*\[\]:]")


def _nombre_hoja(base: str, usados: set[str]) -> str:
    base = _PROHIBIDOS_HOJA.sub(" ", base).strip()[:31] or "Hoja"
    nombre, k = base, 2
    while nombre.lower() in usados:
        sufijo = f" ({k})"
        nombre, k = base[:31 - len(sufijo)] + sufijo, k + 1
    usados.add(nombre.lower())
    return nombre


def _hay_encabezado(filas: list[list[str]]) -> bool:
    """La primera fila es de títulos si tiene varias celdas y ninguna es un número ni una fecha."""
    if len(filas) < 2:
        return False
    primera = [c for c in filas[0] if c]
    return len(primera) >= 2 and all(tipar(c)[1] is None for c in primera)


def _hoja_tabla(ws, filas: list[list[str]]) -> None:
    encabezado = _hay_encabezado(filas)
    cuerpo = filas[1:] if encabezado else filas
    n = max((len(f) for f in filas), default=0)
    anchos = {j: 0 for j in range(1, n + 1)}
    if encabezado:
        for j, texto in enumerate(filas[0], start=1):
            celda = ws.cell(row=1, column=j, value=texto or None)
            celda.font, celda.fill = _CAB_FUENTE, _CAB_RELLENO
            celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            anchos[j] = min(len(texto), 24)
    desde = 2 if encabezado else 1
    for j in range(1, n + 1):  # cada columna se entiende entera: importes, códigos, cantidades con unidad…
        columna = [f[j - 1] if j - 1 < len(f) else "" for f in cuerpo]
        for i, (valor, formato) in enumerate(tipar_columna(columna), start=desde):
            celda = ws.cell(row=i, column=j, value=valor)
            if formato:
                celda.number_format = formato
            anchos[j] = max(anchos[j], len(columna[i - desde]))
    for j, ancho in anchos.items():
        ws.column_dimensions[get_column_letter(j)].width = min(max(ancho + 2, 9), 60)
    if encabezado and n:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(n)}{len(filas)}"


def _sirve_de_nombre(titulo: str) -> bool:
    """El renglón de encima de una tabla le da nombre a su hoja si es un título de verdad y no una
    línea de datos («Precio de venta: $405.00 · Costo: …»)."""
    t = titulo.strip()
    return 3 <= len(t) <= 40 and not any(c in t for c in ":$=·|") and sum(c.isdigit() for c in t) <= 4


def _hoja_lista(ws, cabecera: list[str], filas: list[list], anchos: list[int]) -> None:
    ws.append(cabecera)
    for j, ancho in enumerate(anchos, start=1):
        celda = ws.cell(row=1, column=j)
        celda.font, celda.fill = _CAB_FUENTE, _CAB_RELLENO
        ws.column_dimensions[get_column_letter(j)].width = ancho
    for fila in filas:
        ws.append(fila)
    ws.freeze_panes = "A2"


def tablas_a_excel(tablas: list[Tabla], destino: str | Path, textos: list[str] | None = None, campos=None) -> Path:
    """Un libro con una hoja por tabla (con el título de la tabla por nombre, si lo tiene), una
    hoja «Datos» con los datos sueltos y otra «Comprobaciones» si alguna tabla trae totales. Si no
    hay tablas ni datos y se da el texto de las páginas, va el texto renglón a renglón, para no
    devolver un libro vacío."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    usados: set[str] = {"datos", "comprobaciones", "texto"}
    comprobaciones: list[list] = []
    for n, t in enumerate(tablas, start=1):
        pags = f"p{t.paginas[0]}" + (f"-{t.paginas[-1]}" if len(t.paginas) > 1 else "")
        nombre = _nombre_hoja(t.titulo if _sirve_de_nombre(t.titulo) else f"Tabla {n} ({pags})", usados)
        _hoja_tabla(wb.create_sheet(nombre), t.filas)
        comprobaciones += [[nombre, "Cuadra" if cuadra else "NO CUADRA", detalle] for cuadra, detalle in t.comprobaciones]
    if campos:
        valores = []
        for c in campos:
            valor, formato = tipar(c.valor)
            valores.append([c.nombre, valor if formato in ("num", "int", "fecha") else c.valor, c.pagina,
                            "Etiqueta" if c.origen == "etiqueta" else "Reconocido por su forma"])
        _hoja_lista(wb.create_sheet("Datos"), ["Dato", "Valor", "Página", "Cómo se encontró"], valores, [34, 48, 9, 24])
    if comprobaciones:
        _hoja_lista(wb.create_sheet("Comprobaciones"), ["Hoja", "Resultado", "Detalle"], comprobaciones, [30, 14, 90])
    if not tablas and not campos:
        ws = wb.create_sheet("Texto")
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 110
        ws.append(["Página", "Texto"])
        ws["A1"].font = ws["B1"].font = Font(bold=True)
        for n, texto in enumerate(textos or [], start=1):
            for linea in texto.splitlines():
                if linea.strip():
                    ws.append([n, linea])
    wb.save(str(destino))
    return destino


def a_excel(a: Analisis, destino: str | Path, tablas: list[Tabla] | None = None) -> Path:
    """El Excel que le corresponde al PDF: el de estado de cuenta si se reconoció, o sus tablas."""
    if a.estado is not None and tablas is None:
        return excel.guardar([a.estado], destino)
    return tablas_a_excel(a.tablas if tablas is None else tablas, destino, a.textos, a.campos)


def _guardar_imagen(im: Image.Image, destino: Path, formato: str) -> None:
    tipo, _ = FORMATOS_IMAGEN[formato]
    if tipo == "JPEG":
        if im.mode in ("RGBA", "LA", "P"):
            capa = im.convert("RGBA")
            fondo = Image.new("RGB", capa.size, "white")
            fondo.paste(capa, mask=capa.getchannel("A"))
            im = fondo
        elif im.mode != "RGB":
            im = im.convert("RGB")
        im.save(str(destino), tipo, quality=CALIDAD_JPG)
    else:
        if im.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
            im = im.convert("RGB")
        im.save(str(destino), tipo)


def imagenes(a: Analisis, elegidas: list[ImagenRef], carpeta: str | Path, formato: str = "png",
             progreso: Progreso | None = None) -> tuple[list[Path], list[str]]:
    """Las imágenes incrustadas, tal como están dentro del PDF (a su resolución original).
    Devuelve (archivos escritos, avisos de las que no se pudieron sacar)."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    _, ext = FORMATOS_IMAGEN[formato]
    salidas: list[Path] = []
    avisos: list[str] = []
    ancho = max(2, len(str(max((i.numero for i in elegidas), default=1))))
    with pikepdf.open(str(a.ruta), password=a.clave or "") as pdf:
        for k, ref in enumerate(elegidas):
            destino = carpeta / f"{a.ruta.stem}-imagen-{ref.numero:0{ancho}d}{ext}"
            try:
                im = pikepdf.PdfImage(pdf.get_object(ref.objgen)).as_pil_image()
                _guardar_imagen(im, destino, formato)
                salidas.append(destino)
            except Exception as e:  # noqa: BLE001 - codificaciones que pikepdf o Pillow no saben abrir
                avisos.append(f"imagen {ref.numero} ({ref.donde}): no se pudo sacar ({type(e).__name__})")
            if progreso:
                progreso(k + 1, len(elegidas))
    return salidas, avisos


def paginas(a: Analisis, carpeta: str | Path, formato: str = "png", ppp: int = 150,
            cuales: list[int] | None = None, progreso: Progreso | None = None) -> list[Path]:
    """Cada página (o las de `cuales`, desde 1) como una imagen a `ppp` puntos por pulgada."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    _, ext = FORMATOS_IMAGEN[formato]
    fuente = render.abrir(a.ruta, clave=a.clave)
    salidas: list[Path] = []
    try:
        cuales = cuales or list(range(1, fuente.n_paginas + 1))
        ancho = max(3, len(str(fuente.n_paginas)))
        for k, n in enumerate(cuales):
            destino = carpeta / f"{a.ruta.stem}-pagina-{n:0{ancho}d}{ext}"
            _guardar_imagen(render.pintar(fuente, n - 1, ppp=ppp), destino, formato)
            salidas.append(destino)
            if progreso:
                progreso(k + 1, len(cuales))
    finally:
        fuente.cerrar()
    return salidas


def texto(a: Analisis, destino: str | Path) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    partes = []
    for n, t in enumerate(a.textos, start=1):
        if len(a.textos) > 1:
            partes.append(f"──────── Página {n} ────────")
        partes.append(t.rstrip())
        partes.append("")
    destino.write_text("\n".join(partes), encoding="utf-8-sig")
    return destino


def sello() -> str:
    return f"{datetime.now():%Y%m%d-%H%M}"
