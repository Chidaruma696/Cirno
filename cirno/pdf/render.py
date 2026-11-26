"""Abrir PDF y pintar sus páginas con PDFium (pypdfium2).

PDFium no admite llamadas simultáneas desde varios hilos: todo lo que lo toca pasa por
`CANDADO`. Una `Fuente` es un PDF abierto; las páginas del documento que arma el usuario
apuntan a (fuente, índice) y nunca copian contenido hasta el momento de guardar.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

CANDADO = threading.RLock()

EXT_PDF = (".pdf",)
EXT_IMAGEN = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif")


class ClaveNecesaria(Exception):
    """El PDF está protegido y la contraseña falta o no es correcta."""


class PdfIlegible(Exception):
    """El archivo no se pudo abrir como PDF."""


@dataclass(eq=False)
class Fuente:
    """Un PDF abierto. `nombre` es lo que se enseña; `origen` es el archivo que eligió el usuario
    (distinto de `ruta` cuando la página viene de una imagen convertida a PDF temporal)."""

    ruta: Path
    nombre: str
    origen: Path
    clave: str | None = None
    tamanos: list[tuple[float, float]] = field(default_factory=list)
    _doc: pdfium.PdfDocument | None = field(default=None, repr=False)

    @property
    def n_paginas(self) -> int:
        return len(self.tamanos)

    def cerrar(self) -> None:
        with CANDADO:
            if self._doc is not None:
                self._doc.close()
                self._doc = None


def abrir(ruta: str | Path, clave: str | None = None, nombre: str | None = None,
          origen: str | Path | None = None) -> Fuente:
    ruta = Path(ruta)
    with CANDADO:
        try:
            doc = pdfium.PdfDocument(str(ruta), password=clave)
        except pdfium.PdfiumError as e:
            if "password" in str(e).lower():
                raise ClaveNecesaria(ruta.name) from e
            raise PdfIlegible(f"{ruta.name}: no se pudo abrir como PDF") from e
        except (OSError, ValueError) as e:
            raise PdfIlegible(f"{ruta.name}: {e}") from e
        tamanos = []
        for i in range(len(doc)):
            pagina = doc[i]  # el tamaño que da la página ya cuenta su rotación propia
            tamanos.append(pagina.get_size())
            pagina.close()
    return Fuente(ruta=ruta, nombre=nombre or ruta.name, origen=Path(origen or ruta), clave=clave,
                  tamanos=tamanos, _doc=doc)


def pintar(fuente: Fuente, indice: int, lado_max: int | None = None, ppp: float | None = None) -> Image.Image:
    """La página como imagen RGB. Con `lado_max` cabe en ese cuadro (miniaturas); con `ppp`
    sale a esa resolución (exportar a PNG/JPG)."""
    ancho, alto = fuente.tamanos[indice]
    if ppp:
        escala = ppp / 72.0
    else:
        escala = (lado_max or 240) / max(ancho, alto, 1.0)
    with CANDADO:
        if fuente._doc is None:
            raise PdfIlegible(f"{fuente.nombre}: el archivo ya está cerrado")
        pagina = fuente._doc[indice]
        try:
            mapa = pagina.render(scale=escala)
            imagen = mapa.to_pil()
            mapa.close()
        finally:
            pagina.close()
    return imagen if imagen.mode == "RGB" else imagen.convert("RGB")


def texto(fuente: Fuente, indice: int) -> str:
    """El texto de la página, tal como lo da PDFium (rápido; para buscar, no para sacar tablas)."""
    with CANDADO:
        if fuente._doc is None:
            return ""
        pagina = fuente._doc[indice]
        try:
            hoja = pagina.get_textpage()
            try:
                return hoja.get_text_bounded()
            finally:
                hoja.close()
        finally:
            pagina.close()


def en_blanco(fuente: Fuente, indice: int, tinta_max: float = 0.0015) -> bool:
    """Si la página está vacía a la vista: casi ningún punto oscuro al pintarla en pequeño.
    Tolera el grano de un escaneo, no una línea de texto."""
    gris = pintar(fuente, indice, lado_max=120).convert("L")
    oscuros = sum(gris.histogram()[:215])
    return oscuros / float(gris.width * gris.height) < tinta_max
