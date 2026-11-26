"""Lo que el usuario añade encima de una página: texto, cajas (resaltar, tapar, marco), líneas,
trazos a mano e imágenes. Son datos inmutables, sin Qt ni pikepdf: `gui/pintura.py` los pinta
en pantalla y `marcas_pdf.py` los escribe en el PDF, los dos a partir de lo mismo.

Las coordenadas son puntos de PDF en el «espacio base» de la página: como se ve la página tal
como viene en el archivo (con su giro propio, sin el que añada el usuario), con el origen
arriba a la izquierda y la Y hacia abajo. Así las marcas giran y se recortan con su página.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache

FUENTES_PDF = {
    # (familia, negrita, cursiva) → fuente base de PDF (las catorce que todo visor trae)
    ("sans", False, False): "Helvetica", ("sans", True, False): "Helvetica-Bold",
    ("sans", False, True): "Helvetica-Oblique", ("sans", True, True): "Helvetica-BoldOblique",
    ("serif", False, False): "Times-Roman", ("serif", True, False): "Times-Bold",
    ("serif", False, True): "Times-Italic", ("serif", True, True): "Times-BoldItalic",
    ("mono", False, False): "Courier", ("mono", True, False): "Courier-Bold",
    ("mono", False, True): "Courier-Oblique", ("mono", True, True): "Courier-BoldOblique",
}
ASCENSO = 0.8  # de la parte alta de la caja de texto a la línea base, en cuerpos
INTERLINEA = 1.2  # de una línea base a la siguiente, en cuerpos
AMARILLO = "FFF176"


@dataclass(frozen=True)
class Texto:
    x: float  # ancla: esquina superior izquierda de la caja de texto (o su centro o derecha, según `alineacion`)
    y: float
    texto: str
    cuerpo: float = 12.0
    color: str = "000000"
    fuente: str = "sans"  # sans | serif | mono
    negrita: bool = False
    cursiva: bool = False
    angulo: float = 0.0  # grados en sentido horario, alrededor del ancla
    opacidad: float = 1.0
    alineacion: str = "izq"  # izq | centro | der: qué punto de cada línea cae en x


@dataclass(frozen=True)
class Caja:
    x: float
    y: float
    ancho: float
    alto: float
    relleno: str | None = None
    borde: str | None = None
    grosor: float = 1.0
    opacidad: float = 1.0
    resalte: bool = False  # se mezcla multiplicando, como un rotulador: el texto de debajo sigue legible


@dataclass(frozen=True)
class Linea:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str = "D32F2F"
    grosor: float = 1.5
    flecha: bool = False


@dataclass(frozen=True)
class Trazo:
    puntos: tuple[tuple[float, float], ...]
    color: str = "1A237E"
    grosor: float = 1.5


@dataclass(frozen=True)
class Imagen:
    x: float
    y: float
    ancho: float
    alto: float
    datos: bytes  # el archivo de imagen tal cual (PNG, JPG…)
    angulo: float = 0.0  # grados en sentido horario, alrededor del centro
    opacidad: float = 1.0


Marca = Texto | Caja | Linea | Trazo | Imagen


# ----------------------------------------------------------------------------- texto

def fuente_pdf(m: Texto) -> str:
    return FUENTES_PDF.get((m.fuente, m.negrita, m.cursiva), "Helvetica")


@lru_cache(maxsize=None)
def _anchos(nombre: str) -> dict:
    from pdfminer.fontmetrics import FONT_METRICS  # las métricas AFM de las fuentes base

    return FONT_METRICS[nombre][1]


def ancho_texto(linea: str, m: Texto) -> float:
    """Ancho de una línea en puntos, con las métricas de la fuente base con la que se escribirá."""
    anchos = _anchos(fuente_pdf(m))
    return sum(anchos.get(c, 556) for c in linea) * m.cuerpo / 1000.0


def lineas(m: Texto) -> list[tuple[str, float]]:
    """Cada línea con su desplazamiento en X respecto al ancla, según la alineación."""
    salida = []
    for linea in m.texto.split("\n"):
        ancho = ancho_texto(linea, m)
        dx = 0.0 if m.alineacion == "izq" else (-ancho / 2 if m.alineacion == "centro" else -ancho)
        salida.append((linea, dx))
    return salida


def tamano_texto(m: Texto) -> tuple[float, float, float]:
    """(x mínima relativa al ancla, ancho, alto) de la caja de texto sin girar."""
    filas = lineas(m)
    anchos = [ancho_texto(t, m) for t, _ in filas]
    x_min = min(dx for _, dx in filas)
    ancho = max((dx + a for (_, dx), a in zip(filas, anchos)), default=0.0) - x_min
    return x_min, max(ancho, m.cuerpo * 0.3), m.cuerpo * (INTERLINEA * (len(filas) - 1) + 1.25)


# ----------------------------------------------------------------------------- geometría

def _girar(px: float, py: float, cx: float, cy: float, grados: float) -> tuple[float, float]:
    """Gira (px, py) alrededor de (cx, cy) en sentido horario, con la Y hacia abajo."""
    a = math.radians(grados)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def esquinas(m: Marca) -> list[tuple[float, float]]:
    """Los vértices del contorno de la marca, ya girada, en el espacio base."""
    if isinstance(m, Texto):
        x0, ancho, alto = tamano_texto(m)
        pts = [(m.x + x0, m.y), (m.x + x0 + ancho, m.y), (m.x + x0 + ancho, m.y + alto), (m.x + x0, m.y + alto)]
        return [_girar(px, py, m.x, m.y, m.angulo) for px, py in pts] if m.angulo else pts
    if isinstance(m, Caja):
        return [(m.x, m.y), (m.x + m.ancho, m.y), (m.x + m.ancho, m.y + m.alto), (m.x, m.y + m.alto)]
    if isinstance(m, Linea):
        g = max(m.grosor, 1.0) * (3.0 if m.flecha else 1.0)
        return [(min(m.x1, m.x2) - g, min(m.y1, m.y2) - g), (max(m.x1, m.x2) + g, min(m.y1, m.y2) - g),
                (max(m.x1, m.x2) + g, max(m.y1, m.y2) + g), (min(m.x1, m.x2) - g, max(m.y1, m.y2) + g)]
    if isinstance(m, Trazo):
        xs, ys = [p[0] for p in m.puntos], [p[1] for p in m.puntos]
        g = m.grosor
        return [(min(xs) - g, min(ys) - g), (max(xs) + g, min(ys) - g), (max(xs) + g, max(ys) + g), (min(xs) - g, max(ys) + g)]
    pts = [(m.x, m.y), (m.x + m.ancho, m.y), (m.x + m.ancho, m.y + m.alto), (m.x, m.y + m.alto)]
    if m.angulo:
        cx, cy = m.x + m.ancho / 2, m.y + m.alto / 2
        return [_girar(px, py, cx, cy, m.angulo) for px, py in pts]
    return pts


def caja_de(m: Marca) -> tuple[float, float, float, float]:
    """(x, y, ancho, alto) del rectángulo recto que envuelve a la marca."""
    pts = esquinas(m)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def mover(m: Marca, dx: float, dy: float) -> Marca:
    if isinstance(m, Linea):
        return replace(m, x1=m.x1 + dx, y1=m.y1 + dy, x2=m.x2 + dx, y2=m.y2 + dy)
    if isinstance(m, Trazo):
        return replace(m, puntos=tuple((x + dx, y + dy) for x, y in m.puntos))
    return replace(m, x=m.x + dx, y=m.y + dy)


def punta_flecha(m: Linea) -> list[tuple[float, float]]:
    """El triángulo de la punta, en (x2, y2)."""
    largo = math.hypot(m.x2 - m.x1, m.y2 - m.y1) or 1.0
    ux, uy = (m.x2 - m.x1) / largo, (m.y2 - m.y1) / largo
    t = max(m.grosor * 4.0, 6.0)
    bx, by = m.x2 - ux * t, m.y2 - uy * t
    return [(m.x2, m.y2), (bx - uy * t * 0.45, by + ux * t * 0.45), (bx + uy * t * 0.45, by - ux * t * 0.45)]


def rgb(color: str) -> tuple[float, float, float]:
    c = color.lstrip("#")
    return int(c[0:2], 16) / 255.0, int(c[2:4], 16) / 255.0, int(c[4:6], 16) / 255.0


# ----------------------------------------------------------------------------- marcas hechas

def numero_de_pagina(ancho: float, alto: float, texto: str, posicion: str = "abajo-centro", cuerpo: float = 9.0,
                     margen: float = 24.0, color: str = "444444") -> Texto:
    """El texto de numeración colocado en la página de ese tamaño. `posicion` es arriba|abajo + izq|centro|der."""
    vertical, _, horizontal = posicion.partition("-")
    y = margen - cuerpo * ASCENSO if vertical == "arriba" else alto - margen - cuerpo * ASCENSO
    x = {"izq": margen, "centro": ancho / 2, "der": ancho - margen}[horizontal or "centro"]
    return Texto(x, y, texto, cuerpo=cuerpo, color=color, alineacion=horizontal or "centro")


def marca_de_agua(ancho: float, alto: float, texto: str, color: str = "B71C1C", opacidad: float = 0.18) -> Texto:
    """El texto en diagonal, de esquina a esquina y centrado, que cruza toda la página."""
    diagonal = math.hypot(ancho, alto)
    prueba = Texto(0, 0, texto, cuerpo=100.0, negrita=True)
    cuerpo = max(12.0, min(100.0 * diagonal * 0.62 / max(ancho_texto(texto, prueba), 1.0), min(ancho, alto) * 0.2))
    angulo = -math.degrees(math.atan2(alto, ancho))
    # El ancla es el centro de la línea; para que el texto quede centrado en la página hay que bajar
    # el ancla media caja de texto a lo largo de la perpendicular al texto ya girado.
    cx, cy = ancho / 2, alto / 2
    ax, ay = _girar(cx, cy - cuerpo * 0.625, cx, cy, angulo)
    return Texto(ax, ay, texto, cuerpo=cuerpo, color=color, negrita=True, angulo=angulo, opacidad=opacidad, alineacion="centro")


def a_base(u: float, v: float, zona: tuple[float, float, float, float], rotacion: int) -> tuple[float, float]:
    """Un punto de la página tal como se ve (recortada y girada por el usuario, origen arriba a la
    izquierda) llevado al espacio base."""
    zx, zy, zw, zh = zona
    giro = rotacion % 360
    if giro == 90:
        return zx + v, zy + zh - u
    if giro == 180:
        return zx + zw - u, zy + zh - v
    if giro == 270:
        return zx + zw - v, zy + u
    return zx + u, zy + v


def colocar(m: Texto, zona: tuple[float, float, float, float], rotacion: int) -> Texto:
    """Un texto pensado sobre la página tal como se ve, convertido en marca del espacio base: se
    verá derecho aunque la página esté girada o recortada."""
    x, y = a_base(m.x, m.y, zona, rotacion)
    return replace(m, x=x, y=y, angulo=m.angulo - (rotacion % 360))
