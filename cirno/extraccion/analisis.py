"""Mirar un PDF y decir qué hay dentro que se pueda sacar: si es un estado de cuenta conocido,
qué tablas tiene, qué imágenes lleva incrustadas, cuánto texto y cuántas páginas son solo un
escaneo. No escribe nada; de eso se encarga `exportar`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pdfplumber
import pikepdf

from .. import parser as estados
from . import datos
from .tablas import Tabla, analizar_pagina, componer

# pdfminer avisa por el registro de cada fuente rara que encuentra; no es cosa del usuario.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

LADO_MIN_IMAGEN = 48  # px: por debajo son rayitas, viñetas y adornos

Progreso = Callable[[int, int], None]


class ClaveNecesaria(Exception):
    """El PDF está protegido y la contraseña falta o no es correcta."""


@dataclass
class ImagenRef:
    pagina: int  # primera página donde aparece, desde 1
    numero: int  # orden dentro del documento, desde 1
    ancho: int
    alto: int
    objgen: tuple[int, int]
    nombre: str  # nombre del recurso en la página (/Im0…)

    @property
    def donde(self) -> str:
        return f"página {self.pagina}"


@dataclass
class Analisis:
    ruta: Path
    clave: str | None = None
    n_paginas: int = 0
    estado: estados.EstadoCuenta | None = None  # si es un estado de cuenta reconocido
    tablas: list[Tabla] = field(default_factory=list)
    imagenes: list[ImagenRef] = field(default_factory=list)
    textos: list[str] = field(default_factory=list)  # el texto de cada página
    campos: list[datos.Campo] = field(default_factory=list)  # datos sueltos: «Cliente: Fulano», RFC, totales…
    tipo: str = ""  # qué parece el documento («Factura (CFDI)», «Cotización»…), si se sabe
    paginas_sin_texto: list[int] = field(default_factory=list)
    error: str = ""

    @property
    def n_palabras(self) -> int:
        return sum(len(t.split()) for t in self.textos)

    @property
    def escaneado(self) -> bool:
        return self.n_paginas > 0 and len(self.paginas_sin_texto) == self.n_paginas

    def resumen(self) -> str:
        if self.error:
            return f"✗ {self.error}"
        partes = [self.tipo] if self.tipo and not self.estado else []
        if self.estado:
            ec = self.estado
            partes.append(f"estado de cuenta {ec.cuenta or ''}".strip() + f" · {len(ec.movimientos)} movimientos")
        elif self.tablas:
            partes.append("1 tabla" if len(self.tablas) == 1 else f"{len(self.tablas)} tablas")
        if self.campos and not self.estado:
            partes.append("1 dato" if len(self.campos) == 1 else f"{len(self.campos)} datos")
        if self.imagenes:
            partes.append("1 imagen" if len(self.imagenes) == 1 else f"{len(self.imagenes)} imágenes")
        partes.append("1 página" if self.n_paginas == 1 else f"{self.n_paginas} páginas")
        if self.escaneado:
            partes.append("escaneado, sin texto")
        elif self.paginas_sin_texto:
            partes.append(f"{len(self.paginas_sin_texto)} sin texto")
        return " · ".join(partes)


def _imagenes(ruta: Path, clave: str | None) -> list[ImagenRef]:
    """Las imágenes incrustadas, una vez cada una aunque se repita en todas las páginas (logotipos)."""
    salida: list[ImagenRef] = []
    vistas: set[tuple[int, int]] = set()
    try:
        pdf = pikepdf.open(str(ruta), password=clave or "")
    except pikepdf.PdfError:
        return salida
    with pdf:
        for n, pagina in enumerate(pdf.pages, start=1):
            try:
                recursos = list(pagina.get_images().items())  # incluye las que van dentro de formularios
            except Exception:  # noqa: BLE001 - recursos rotos en una página
                continue
            for nombre, objeto in recursos:
                try:
                    if objeto.objgen in vistas or objeto.get("/ImageMask", False):
                        continue
                    ancho, alto = int(objeto.Width), int(objeto.Height)
                except Exception:  # noqa: BLE001
                    continue
                vistas.add(objeto.objgen)
                if min(ancho, alto) >= LADO_MIN_IMAGEN:
                    salida.append(ImagenRef(n, len(salida) + 1, ancho, alto, tuple(objeto.objgen), str(nombre)))
    return salida


def analizar(ruta: str | Path, clave: str | None = None, progreso: Progreso | None = None,
             cancelar: Callable[[], bool] | None = None) -> Analisis:
    ruta = Path(ruta)
    a = Analisis(ruta=ruta, clave=clave)
    try:
        pdf = pdfplumber.open(str(ruta), password=clave or None)
    except Exception as e:  # noqa: BLE001 - pdfminer lanza clases distintas según la versión
        if "password" in type(e).__name__.lower() or "password" in str(e).lower() or "encrypt" in type(e).__name__.lower():
            raise ClaveNecesaria(ruta.name) from e
        a.error = "no se pudo abrir como PDF"
        return a

    ec = estados.EstadoCuenta(archivo=ruta)
    por_pagina = []
    sueltos: list[datos.Campo] = []
    with pdf:
        a.n_paginas = len(pdf.pages)
        for n, page in enumerate(pdf.pages, start=1):
            if cancelar and cancelar():
                a.error = "cancelado"
                return a
            if progreso:
                progreso(n - 1, a.n_paginas)
            try:
                palabras = page.extract_words()
                texto = page.extract_text() or ""
            except Exception:  # noqa: BLE001 - una página rota no debe perder las demás
                palabras, texto = [], ""
            a.textos.append(texto)
            if not palabras:
                a.paginas_sin_texto.append(n)
                por_pagina.append(([], []))
            else:
                escala = (page.width or estados.PAGE_WIDTH_REF) / estados.PAGE_WIDTH_REF
                estados.leer_palabras(ec, palabras, escala)
                por_pagina.append(analizar_pagina(page, n, palabras))
                try:
                    sueltos += datos.campos_de_pagina(palabras, texto, n)
                except Exception:  # noqa: BLE001 - los datos sueltos son un extra: no deben tumbar el análisis
                    pass
            page.flush_cache()

    if ec.movimientos or ec.saldo_final:
        estados.validar(ec)
        a.estado = ec
    a.tablas = componer(por_pagina)
    a.campos = datos.unir(sueltos)
    a.tipo = datos.tipo_documento(a.textos)
    a.imagenes = _imagenes(ruta, clave)
    if progreso:
        progreso(a.n_paginas, a.n_paginas)
    return a
