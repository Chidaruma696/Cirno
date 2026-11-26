"""Escribir las marcas dentro del PDF: se añaden al contenido de la página como dibujo normal
(texto con las fuentes base, rectángulos, líneas, imágenes), no como anotaciones, para que se
vean igual en cualquier visor y al imprimir. También aplica el recorte."""

from __future__ import annotations

import hashlib
import io
import math

import pikepdf
from PIL import Image, ImageOps

from . import borrar
from .marcas import ASCENSO, INTERLINEA, Caja, Imagen, Linea, Texto, Trazo, _girar, fuente_pdf, lineas, punta_flecha, rgb

Nombre = pikepdf.Name


def _n(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") or "0"


def _cadena(texto: str) -> bytes:
    crudo = texto.encode("cp1252", errors="replace")
    return b"(" + crudo.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def caja_visible(page: pikepdf.Page) -> tuple[float, float, float, float]:
    """La parte de la página que se ve (CropBox dentro de MediaBox), en el espacio del PDF."""
    media = [float(v) for v in page.mediabox]
    recorte = [float(v) for v in page.cropbox]
    x0, x1 = sorted((media[0], media[2]))
    y0, y1 = sorted((media[1], media[3]))
    cx0, cx1 = sorted((recorte[0], recorte[2]))
    cy0, cy1 = sorted((recorte[1], recorte[3]))
    caja = (max(x0, cx0), max(y0, cy0), min(x1, cx1), min(y1, cy1))
    return caja if caja[2] > caja[0] and caja[3] > caja[1] else (x0, y0, x1, y1)


def giro_propio(page: pikepdf.Page) -> int:
    try:
        return int(page.obj.get("/Rotate", 0)) % 360
    except (TypeError, ValueError):
        return 0


def matriz_base(page: pikepdf.Page) -> tuple[tuple[float, ...], float, float]:
    """(matriz, ancho, alto): la matriz lleva del espacio base con la Y hacia arriba (origen en la
    esquina inferior izquierda de la página tal como se ve) al espacio del PDF; ancho y alto son
    los de la página tal como se ve."""
    x0, y0, x1, y1 = caja_visible(page)
    giro = giro_propio(page)
    if giro == 90:
        return (0, 1, -1, 0, x1, y0), y1 - y0, x1 - x0
    if giro == 180:
        return (-1, 0, 0, -1, x1, y1), x1 - x0, y1 - y0
    if giro == 270:
        return (0, -1, 1, 0, x0, y1), y1 - y0, x1 - x0
    return (1, 0, 0, 1, x0, y0), x1 - x0, y1 - y0


def objeto_imagen(pdf: pikepdf.Pdf, datos: bytes) -> pikepdf.Stream:
    """La imagen como objeto del PDF. Los JPEG entran tal cual; lo demás sin pérdida, y la
    transparencia va en su máscara."""
    im = Image.open(io.BytesIO(datos))
    im.load()
    recta = ImageOps.exif_transpose(im)
    if im.format == "JPEG" and im.mode in ("L", "RGB") and recta.size == im.size and recta.tobytes() == im.tobytes():
        espacio = Nombre.DeviceGray if im.mode == "L" else Nombre.DeviceRGB
        return pikepdf.Stream(pdf, datos, Type=Nombre.XObject, Subtype=Nombre.Image, Width=im.width, Height=im.height,
                              ColorSpace=espacio, BitsPerComponent=8, Filter=Nombre.DCTDecode)
    im = recta
    mascara = None
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        capa = im.convert("RGBA")
        alfa = capa.getchannel("A")
        if alfa.getextrema()[0] < 255:
            mascara = pikepdf.Stream(pdf, alfa.tobytes(), Type=Nombre.XObject, Subtype=Nombre.Image, Width=im.width,
                                     Height=im.height, ColorSpace=Nombre.DeviceGray, BitsPerComponent=8)
        im = capa.convert("RGB")
    elif im.mode not in ("L", "RGB"):
        im = im.convert("RGB")
    espacio = Nombre.DeviceGray if im.mode == "L" else Nombre.DeviceRGB
    objeto = pikepdf.Stream(pdf, im.tobytes(), Type=Nombre.XObject, Subtype=Nombre.Image, Width=im.width, Height=im.height,
                            ColorSpace=espacio, BitsPerComponent=8)
    if mascara is not None:
        objeto.SMask = mascara
    return objeto


class _Recursos:
    """Los recursos que las marcas necesitan en la página, con nombres que no chocan con los suyos."""

    def __init__(self, pdf: pikepdf.Pdf, page: pikepdf.Page, imagenes: dict) -> None:
        self.pdf, self.imagenes = pdf, imagenes
        previos = page.obj.get("/Resources")
        # Copia propia: varias páginas pueden compartir el mismo diccionario de recursos.
        self.raiz = pikepdf.Dictionary(previos) if previos is not None else pikepdf.Dictionary()
        for clave in ("/Font", "/XObject", "/ExtGState"):
            sub = self.raiz.get(clave)
            self.raiz[clave] = pikepdf.Dictionary(sub) if sub is not None else pikepdf.Dictionary()
        page.obj.Resources = self.raiz
        self._hechos: dict = {}

    def _nombre(self, tipo: str, clave, crear) -> str:
        if (tipo, clave) not in self._hechos:
            sub = self.raiz[tipo]
            k = 1
            while f"/Cirno{k}" in sub:
                k += 1
            sub[f"/Cirno{k}"] = crear()
            self._hechos[(tipo, clave)] = f"/Cirno{k}"
        return self._hechos[(tipo, clave)]

    def fuente(self, base: str) -> str:
        return self._nombre("/Font", base, lambda: self.pdf.make_indirect(pikepdf.Dictionary(
            Type=Nombre.Font, Subtype=Nombre.Type1, BaseFont=Nombre("/" + base), Encoding=Nombre.WinAnsiEncoding)))

    def estado(self, opacidad: float, resalte: bool) -> str:
        def crear():
            d = pikepdf.Dictionary(Type=Nombre.ExtGState, ca=opacidad, CA=opacidad)
            if resalte:
                d.BM = Nombre.Multiply
            return d
        return self._nombre("/ExtGState", (round(opacidad, 3), resalte), crear)

    def imagen(self, datos: bytes) -> str:
        huella = hashlib.sha1(datos).digest()
        if huella not in self.imagenes:  # la misma imagen en varias páginas es un solo objeto
            self.imagenes[huella] = self.pdf.make_indirect(objeto_imagen(self.pdf, datos))
        return self._nombre("/XObject", huella, lambda: self.imagenes[huella])


def _dibujo(marcas, alto: float, rec: _Recursos) -> bytes:
    """Las órdenes de dibujo de las marcas, en el espacio base con la Y hacia arriba."""
    o: list[bytes] = []

    def sumar(texto: str) -> None:
        o.append(texto.encode("ascii"))

    def color(c: str, trazo: bool = False) -> str:
        r, g, b = rgb(c)
        return f"{_n(r)} {_n(g)} {_n(b)} {'RG' if trazo else 'rg'}"

    for m in marcas:
        sumar("q")
        opacidad = getattr(m, "opacidad", 1.0)
        resalte = getattr(m, "resalte", False)
        if opacidad < 0.999 or resalte:
            sumar(f"{rec.estado(opacidad, resalte)} gs")
        if isinstance(m, Texto):
            a = math.radians(m.angulo)
            cos, sen = math.cos(a), math.sin(a)
            sumar(f"{color(m.color)} BT {rec.fuente(fuente_pdf(m))} {_n(m.cuerpo)} Tf")
            for i, (linea, dx) in enumerate(lineas(m)):
                bx, by = _girar(m.x + dx, m.y + (ASCENSO + INTERLINEA * i) * m.cuerpo, m.x, m.y, m.angulo)
                sumar(f"{_n(cos)} {_n(-sen)} {_n(sen)} {_n(cos)} {_n(bx)} {_n(alto - by)} Tm")
                o.append(_cadena(linea) + b" Tj")
            sumar("ET")
        elif isinstance(m, Caja):
            sumar(f"{_n(m.x)} {_n(alto - m.y - m.alto)} {_n(m.ancho)} {_n(m.alto)} re")
            if m.relleno and m.borde:
                o.insert(-1, f"{color(m.relleno)} {color(m.borde, True)} {_n(m.grosor)} w".encode("ascii"))
                sumar("B")
            elif m.relleno:
                o.insert(-1, color(m.relleno).encode("ascii"))
                sumar("f")
            else:
                o.insert(-1, f"{color(m.borde or '000000', True)} {_n(m.grosor)} w".encode("ascii"))
                sumar("S")
        elif isinstance(m, Linea):
            sumar(f"{color(m.color, True)} {color(m.color)} {_n(m.grosor)} w 1 J")
            x2, y2 = m.x2, m.y2
            if m.flecha:  # la raya acaba en la base de la punta, no en su vértice
                punta = punta_flecha(m)
                x2, y2 = (punta[1][0] + punta[2][0]) / 2, (punta[1][1] + punta[2][1]) / 2
            sumar(f"{_n(m.x1)} {_n(alto - m.y1)} m {_n(x2)} {_n(alto - y2)} l S")
            if m.flecha:
                (ax, ay), (bx, by), (cx, cy) = punta
                sumar(f"{_n(ax)} {_n(alto - ay)} m {_n(bx)} {_n(alto - by)} l {_n(cx)} {_n(alto - cy)} l h f")
        elif isinstance(m, Trazo):
            if not m.puntos:
                o.pop()
                continue
            sumar(f"{color(m.color, True)} {_n(m.grosor)} w 1 J 1 j")
            (x, y), resto = m.puntos[0], m.puntos[1:]
            sumar(f"{_n(x)} {_n(alto - y)} m")
            for x, y in resto or [(x, y)]:
                sumar(f"{_n(x)} {_n(alto - y)} l")
            sumar("S")
        elif isinstance(m, Imagen):
            a = math.radians(-m.angulo)  # antihorario en el espacio con la Y hacia arriba
            cos, sen = math.cos(a), math.sin(a)
            cx, cy = m.x + m.ancho / 2, alto - m.y - m.alto / 2
            e = cx - m.ancho / 2 * cos + m.alto / 2 * sen
            f = cy - m.ancho / 2 * sen - m.alto / 2 * cos
            sumar(f"{_n(m.ancho * cos)} {_n(m.ancho * sen)} {_n(-m.alto * sen)} {_n(m.alto * cos)} {_n(e)} {_n(f)} cm "
                  f"{rec.imagen(m.datos)} Do")
        sumar("Q")
    return b"\n".join(o)


def aplicar(pdf: pikepdf.Pdf, page: pikepdf.Page, marcas=(), recorte=None, imagenes: dict | None = None) -> None:
    """Dibuja las marcas en la página y la recorta. `imagenes` es la caché de imágenes del documento."""
    if not marcas and not recorte:
        return
    matriz, _ancho, alto = matriz_base(page)
    if marcas:
        rec = _Recursos(pdf, page, imagenes if imagenes is not None else {})
        # Lo que queda bajo una caja opaca se borra del contenido antes de dibujarla: tapar es quitar.
        a, b, c, d, e, f = matriz
        tapas = []
        for m in marcas:
            if isinstance(m, Caja) and m.relleno and not m.resalte and m.opacidad >= 0.999:
                pts = [(a * u + c * v + e, b * u + d * v + f)
                       for u, v in ((m.x, alto - m.y - m.alto), (m.x + m.ancho, alto - m.y))]
                tapas.append((min(pts[0][0], pts[1][0]), min(pts[0][1], pts[1][1]),
                              max(pts[0][0], pts[1][0]), max(pts[0][1], pts[1][1]), m.relleno))
        if tapas:
            try:
                borrar.bajo_las_tapas(pdf, page, tapas, rec.raiz)
            except Exception:  # noqa: BLE001 - si el contenido no se deja leer, queda tapado sin borrar
                pass
        dibujo = _dibujo(marcas, alto, rec)
        # El contenido original se encierra entre q y Q para que su estado gráfico no afecte a lo añadido.
        page.contents_add(b"q\n", prepend=True)
        page.contents_add(b"\nQ\nq " + " ".join(_n(v) for v in matriz).encode("ascii") + b" cm\n" + dibujo + b"\nQ\n")
    if recorte:
        x, y, ancho_r, alto_r = recorte
        a, b, c, d, e, f = matriz
        pts = [(a * u + c * v + e, b * u + d * v + f)
               for u, v in ((x, alto - y - alto_r), (x + ancho_r, alto - y))]
        caja = pikepdf.Array([min(pts[0][0], pts[1][0]), min(pts[0][1], pts[1][1]),
                              max(pts[0][0], pts[1][0]), max(pts[0][1], pts[1][1])])
        page.obj.MediaBox = caja
        page.obj.CropBox = caja
        for sobra in ("/TrimBox", "/BleedBox", "/ArtBox"):
            if sobra in page.obj:
                del page.obj[sobra]
