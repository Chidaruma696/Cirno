"""Escribir el resultado con pikepdf: unir, reordenar, girar, marcas y recortes, dividir,
contraseña, propiedades, reducir el tamaño, e imágenes como páginas.

Los originales nunca se tocan: el destino no puede ser uno de los PDF de los que salen las
páginas (además, mientras están abiertos Windows no dejaría reemplazarlos).
"""

from __future__ import annotations

import io
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pikepdf
from PIL import Image, ImageOps

from . import marcas_pdf
from .documento import Pagina

Progreso = Callable[[int, int], None]

PPP_IMAGEN = 96.0  # resolución que se supone a una imagen que no dice la suya
LADO_MAX_PT = 14400.0  # límite de tamaño de página de PDF

# Reducir tamaño: (puntos por pulgada a los que se dejan las imágenes, calidad JPEG)
NIVELES_REDUCIR = {"pantalla": (96, 60), "correo": (150, 72), "impresion": (220, 82)}

# «Página 1 de 7», «Hoja 1/3», «Pág. 1 de 2», «Page 1 of 4»: donde empieza un documento
_PRIMERA_PAGINA = re.compile(r"(?i)\b(?:p[áa]g(?:ina)?s?\.?|hoja|page)\s*:?\s*0*1\s*(?:de|/|of)\s*\d+")


class ErrorGuardar(Exception):
    """No se pudo escribir el PDF, con un motivo que se le puede enseñar al usuario."""


@dataclass
class OpcionesPdf:
    titulo: str = ""
    autor: str = ""
    asunto: str = ""
    palabras: str = ""
    clave: str = ""  # contraseña para abrir el PDF que se escribe
    reducir: str = ""  # "" | pantalla | correo | impresion

    @property
    def con_propiedades(self) -> bool:
        return any((self.titulo, self.autor, self.asunto, self.palabras))

    def resumen(self) -> str:
        partes = []
        if self.clave:
            partes.append("con contraseña")
        if self.reducir:
            partes.append("tamaño reducido")
        if self.con_propiedades:
            partes.append("con propiedades")
        return " · ".join(partes)


def _misma(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a).lower() == str(b).lower()


def _comprobar_destino(paginas: list[Pagina], destinos: list[Path]) -> None:
    fuentes = {p.fuente.ruta for p in paginas} | {p.fuente.origen for p in paginas}
    for d in destinos:
        if any(_misma(d, f) for f in fuentes):
            raise ErrorGuardar(f"«{d.name}» es uno de los archivos de origen. Cirno no escribe encima de "
                               "los originales: elige otro nombre.")


def reducir_imagenes(pdf: pikepdf.Pdf, nivel: str) -> int:
    """Baja de resolución y recomprime como JPEG las imágenes grandes (las de un escaneo, sobre todo).
    Solo toca las que entiende sin riesgo (gris o color de 8 bits, sin máscara) y solo si el
    resultado ocupa menos. Devuelve cuántas cambió."""
    ppp, calidad = NIVELES_REDUCIR[nivel]
    hechas = 0
    vistas: set = set()
    for pagina in pdf.pages:
        x0, y0, x1, y1 = marcas_pdf.caja_visible(pagina)
        tope = max(abs(x1 - x0), abs(y1 - y0)) / 72.0 * ppp  # píxeles del lado largo de la página a esa resolución
        try:
            recursos = list(pagina.get_images().values())
        except Exception:  # noqa: BLE001
            continue
        for objeto in recursos:
            try:
                if objeto.objgen in vistas:
                    continue
                vistas.add(objeto.objgen)
                if (objeto.get("/ImageMask", False) or "/SMask" in objeto or "/Mask" in objeto or "/Decode" in objeto
                        or int(objeto.get("/BitsPerComponent", 0)) != 8):
                    continue
                antes = len(objeto.read_raw_bytes())
                im = pikepdf.PdfImage(objeto).as_pil_image()
                if im.mode not in ("L", "RGB"):
                    continue
                escala = min(1.0, tope / max(im.width, im.height))
                if escala < 0.95:
                    im = im.resize((max(1, round(im.width * escala)), max(1, round(im.height * escala))), Image.LANCZOS)
                salida = io.BytesIO()
                im.save(salida, "JPEG", quality=calidad, optimize=True)
                if salida.tell() >= antes * 0.9:
                    continue
                objeto.write(salida.getvalue(), filter=pikepdf.Name.DCTDecode)
                objeto.Width, objeto.Height = im.width, im.height
                objeto.ColorSpace = pikepdf.Name.DeviceGray if im.mode == "L" else pikepdf.Name.DeviceRGB
                hechas += 1
            except Exception:  # noqa: BLE001 - una imagen rara se deja como está
                continue
    return hechas


def _propiedades(salida: pikepdf.Pdf, abiertos: dict, paginas: list[Pagina], op: OpcionesPdf) -> None:
    """Título, autor… Si no se dan y todo sale de un solo PDF, se conservan los suyos."""
    fuentes = {id(p.fuente) for p in paginas}
    if len(fuentes) == 1:
        try:
            for clave, valor in abiertos[next(iter(fuentes))].docinfo.items():
                if clave in ("/Title", "/Author", "/Subject", "/Keywords"):
                    salida.docinfo[clave] = str(valor)
        except Exception:  # noqa: BLE001 - metadatos rotos en el origen
            pass
    for clave, valor in (("/Title", op.titulo), ("/Author", op.autor), ("/Subject", op.asunto), ("/Keywords", op.palabras)):
        if valor:
            salida.docinfo[clave] = valor
    salida.docinfo["/Producer"] = "Cirno"


def _volcar(paginas: list[Pagina], destino: Path, abiertos: dict, progreso: Progreso | None,
            hecho: int, total: int, op: OpcionesPdf) -> int:
    salida = pikepdf.Pdf.new()
    usadas: set[tuple[int, int]] = set()
    # Primero se traen todas las páginas, y solo después se giran y se dibujan: la misma página
    # usada dos veces comparte objetos hasta que se le da un diccionario propio.
    i = 0
    while i < len(paginas):
        j = i
        while j < len(paginas) and paginas[j].fuente is paginas[i].fuente:
            j += 1
        lote, clave = paginas[i:j], id(paginas[i].fuente)
        if clave not in abiertos:
            abiertos[clave] = pikepdf.open(str(lote[0].fuente.ruta), password=lote[0].fuente.clave or "")
        origen = abiertos[clave]
        antes = len(salida.pages)
        try:
            # Copia de alto nivel: conserva los marcadores y los campos de formulario de esas páginas.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                salida.add_pages_from(origen, [p.indice for p in lote])
            if len(salida.pages) - antes != len(lote):
                raise ValueError("no se copiaron todas")
        except Exception:  # noqa: BLE001 - versiones de pikepdf sin esa copia, o un PDF que no la admite
            del salida.pages[antes:]
            for p in lote:
                salida.pages.append(origen.pages[p.indice])
        for k, p in enumerate(lote):
            if (clave, p.indice) in usadas:
                salida.pages[antes + k] = pikepdf.Page(salida.make_indirect(pikepdf.Dictionary(salida.pages[antes + k].obj)))
            usadas.add((clave, p.indice))
        i = j
    imagenes: dict = {}
    for p, nueva in zip(paginas, salida.pages):
        marcas_pdf.aplicar(salida, nueva, p.marcas, p.recorte, imagenes)
        if p.rotacion % 360:
            nueva.rotate(p.rotacion % 360, relative=True)
        hecho += 1
        if progreso:
            progreso(hecho, total)
    if op.reducir:
        reducir_imagenes(salida, op.reducir)
    _propiedades(salida, abiertos, paginas, op)
    destino.parent.mkdir(parents=True, exist_ok=True)
    salida.remove_unreferenced_resources()
    cifrado = pikepdf.Encryption(owner=op.clave, user=op.clave, R=6) if op.clave else False
    salida.save(str(destino), encryption=cifrado, object_stream_mode=pikepdf.ObjectStreamMode.generate,
                recompress_flate=bool(op.reducir))
    salida.close()
    return hecho


def _escribir(grupos: list[list[Pagina]], destinos: list[Path], progreso: Progreso | None, op: OpcionesPdf | None) -> None:
    todas = [p for g in grupos for p in g]
    _comprobar_destino(todas, destinos)
    abiertos: dict = {}
    hecho = 0
    try:
        for grupo, destino in zip(grupos, destinos):
            hecho = _volcar(grupo, destino, abiertos, progreso, hecho, len(todas), op or OpcionesPdf())
    except PermissionError as e:
        raise ErrorGuardar("No se pudo escribir (¿el PDF de destino está abierto en otro programa?).") from e
    except pikepdf.PdfError as e:
        raise ErrorGuardar(f"No se pudo escribir el PDF: {e}") from e
    finally:
        for pdf in abiertos.values():
            pdf.close()


def guardar(paginas: list[Pagina], destino: str | Path, progreso: Progreso | None = None,
            opciones: OpcionesPdf | None = None) -> Path:
    """Todas las páginas, en su orden, con sus giros, marcas y recortes, en un solo PDF."""
    destino = Path(destino)
    if not paginas:
        raise ErrorGuardar("No hay páginas que guardar.")
    _escribir([list(paginas)], [destino], progreso, opciones)
    return destino


def nombres_division(n_partes: int, carpeta: Path, base: str) -> list[Path]:
    ancho = max(2, len(str(n_partes)))
    return [carpeta / f"{base}-{i:0{ancho}d}.pdf" for i in range(1, n_partes + 1)]


def grupos_cada(paginas: list, cada: int) -> list[list]:
    cada = max(1, int(cada))
    return [paginas[i:i + cada] for i in range(0, len(paginas), cada)]


def grupos_por_inicio(paginas: list, inicios: list[int]) -> list[list]:
    """Parte la lista en los índices dados (cada uno es la primera página de un documento)."""
    cortes = sorted({0, *[i for i in inicios if 0 < i < len(paginas)]}) + [len(paginas)]
    return [paginas[a:b] for a, b in zip(cortes, cortes[1:])]


def inicios_de_documento(textos: list[str]) -> list[int]:
    """Las páginas (desde 0) cuyo texto dice «Página 1 de N»: ahí empieza un documento."""
    return [i for i, t in enumerate(textos) if _PRIMERA_PAGINA.search(t or "")]


def dividir(paginas: list[Pagina], carpeta: str | Path, base: str, cada: int = 1,
            progreso: Progreso | None = None, opciones: OpcionesPdf | None = None,
            grupos: list[list[Pagina]] | None = None) -> list[Path]:
    """Varios PDF: uno por cada `cada` páginas (base-01.pdf, base-02.pdf…), o uno por cada grupo dado."""
    carpeta = Path(carpeta)
    if not paginas:
        raise ErrorGuardar("No hay páginas que dividir.")
    grupos = grupos if grupos is not None else grupos_cada(list(paginas), cada)
    destinos = nombres_division(len(grupos), carpeta, base)
    _escribir(grupos, destinos, progreso, opciones)
    return destinos


def imagen_a_pdf(imagen: str | Path, destino: str | Path) -> Path:
    """Una imagen como PDF de una página, al tamaño que le corresponde por su resolución. Los JPEG
    se incrustan tal cual, sin recomprimir; lo demás va sin pérdida."""
    imagen, destino = Path(imagen), Path(destino)
    try:
        datos = imagen.read_bytes()
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(datos)))
        pdf = pikepdf.Pdf.new()
        objeto = marcas_pdf.objeto_imagen(pdf, datos)
    except Exception as e:  # noqa: BLE001 - Pillow lanza de todo según el formato
        raise ErrorGuardar(f"{imagen.name}: no se pudo leer la imagen") from e

    ppp = im.info.get("dpi") or (PPP_IMAGEN, PPP_IMAGEN)
    try:
        ppp_x, ppp_y = float(ppp[0]), float(ppp[1])
    except (TypeError, ValueError, IndexError):
        ppp_x = ppp_y = PPP_IMAGEN
    if ppp_x < 30 or ppp_y < 30:
        ppp_x = ppp_y = PPP_IMAGEN
    ancho_pt, alto_pt = im.width * 72.0 / ppp_x, im.height * 72.0 / ppp_y
    exceso = max(ancho_pt, alto_pt) / LADO_MAX_PT
    if exceso > 1:
        ancho_pt, alto_pt = ancho_pt / exceso, alto_pt / exceso

    pagina = pdf.add_blank_page(page_size=(ancho_pt, alto_pt))
    pagina.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=objeto))
    pagina.Contents = pdf.make_stream(f"q {ancho_pt:.3f} 0 0 {alto_pt:.3f} 0 0 cm /Im0 Do Q".encode("ascii"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(destino))
    pdf.close()
    return destino
