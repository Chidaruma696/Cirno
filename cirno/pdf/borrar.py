"""Borrar de verdad lo que queda debajo de una tapa.

Dibujar un rectángulo encima de un dato no lo quita del PDF: el texto sigue ahí, se puede
buscar, copiar o destapar. Aquí se recorre el contenido de la página siguiendo la posición de
cada letra (matrices, fuente, espaciados) y se eliminan las que caen bajo una tapa; en las
imágenes (un escaneo) se pinta la zona tapada dentro de la propia imagen.

Lo que no se sabe medir con seguridad se deja como estaba (queda tapado, no borrado): fuentes
con codificaciones raras, y el texto metido dentro de formularios (Form XObject).
"""

from __future__ import annotations

import io

import pikepdf
from PIL import Image, ImageDraw

Matriz = tuple[float, float, float, float, float, float]
IDENTIDAD: Matriz = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _por(m: Matriz, n: Matriz) -> Matriz:
    """m × n: aplicar primero m y luego n (convención de PDF, vectores fila)."""
    a, b, c, d, e, f = m
    g, h, i, j, k, l = n  # noqa: E741
    return (a * g + b * i, a * h + b * j, c * g + d * i, c * h + d * j, e * g + f * i + k, e * h + f * j + l)


def _punto(m: Matriz, x: float, y: float) -> tuple[float, float]:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _inversa(m: Matriz) -> Matriz | None:
    a, b, c, d, e, f = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    return (d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det)


class _Fuente:
    """Lo justo de una fuente para saber cuánto avanza cada letra."""

    def __init__(self, d) -> None:
        self.ok = True
        self.n_bytes = 1
        self.anchos: dict[int, float] = {}
        self.defecto = 500.0
        self._base = None
        try:
            tipo = str(d.get("/Subtype"))
            if tipo == "/Type0":
                if str(d.get("/Encoding")) not in ("/Identity-H",):
                    self.ok = False
                    return
                self.n_bytes = 2
                hija = d.DescendantFonts[0]
                self.defecto = float(hija.get("/DW", 1000))
                w = list(hija.get("/W", []))
                i = 0
                while i < len(w):
                    primero = int(w[i])
                    if isinstance(w[i + 1], pikepdf.Array):
                        for k, ancho in enumerate(w[i + 1]):
                            self.anchos[primero + k] = float(ancho)
                        i += 2
                    else:
                        for codigo in range(primero, int(w[i + 1]) + 1):
                            self.anchos[codigo] = float(w[i + 2])
                        i += 3
            elif tipo in ("/Type1", "/TrueType", "/MMType1", "/Type3"):
                anchos = d.get("/Widths")
                # Las Type3 (las que escribe Chrome al imprimir a PDF) miden en su propio espacio de glifo.
                factor = float(d.FontMatrix[0]) * 1000.0 if tipo == "/Type3" else 1.0
                if anchos is not None:
                    primero = int(d.get("/FirstChar", 0))
                    for k, ancho in enumerate(anchos):
                        self.anchos[primero + k] = float(ancho) * factor
                    descriptor = d.get("/FontDescriptor")
                    self.defecto = float(descriptor.get("/MissingWidth", 0)) * factor if descriptor is not None else 0.0
                elif tipo == "/Type3":
                    self.ok = False
                else:  # una de las catorce fuentes base: sus anchos son conocidos
                    from pdfminer.fontmetrics import FONT_METRICS

                    self._base = FONT_METRICS.get(str(d.get("/BaseFont", "/Helvetica")).lstrip("/"), FONT_METRICS["Helvetica"])[1]
            else:
                self.ok = False
        except Exception:  # noqa: BLE001 - fuente mal formada: no se toca su texto
            self.ok = False

    def ancho(self, codigo: int) -> float:
        if self._base is not None:
            return float(self._base.get(bytes([codigo & 0xFF]).decode("cp1252", "replace"), 500))
        return self.anchos.get(codigo, self.defecto)


class _Estado:
    def __init__(self) -> None:
        self.ctm: Matriz = IDENTIDAD
        self.fuente: _Fuente | None = None
        self.cuerpo = 0.0
        self.tc = self.tw = self.tl = self.ts = 0.0
        self.th = 1.0

    def copia(self) -> "_Estado":
        otro = _Estado()
        otro.__dict__.update(self.__dict__)
        return otro


def _dentro(x: float, y: float, tapas) -> bool:
    return any(t[0] <= x <= t[2] and t[1] <= y <= t[3] for t in tapas)


def _pintar_imagen(pdf, objeto, ctm: Matriz, tapas, lienzos: dict):
    """Pinta en la imagen la parte que cae bajo alguna tapa. Devuelve True si tocó algo."""
    inversa = _inversa(ctm)
    if inversa is None:
        return False
    clave = objeto.objgen
    tocada = False
    for x0, y0, x1, y1, tinta in tapas:
        esquinas = [_punto(inversa, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        us, vs = [p[0] for p in esquinas], [p[1] for p in esquinas]
        if max(us) <= 0 or min(us) >= 1 or max(vs) <= 0 or min(vs) >= 1:
            continue
        if clave not in lienzos:
            if objeto.get("/ImageMask", False) or "/SMask" in objeto or "/Mask" in objeto:
                return False
            im = pikepdf.PdfImage(objeto).as_pil_image()
            if im.mode not in ("1", "L", "RGB"):
                return False
            lienzos[clave] = [im.copy(), objeto, im.mode]
        im = lienzos[clave][0]
        if im.mode == "1":  # para pintar hace falta gris; al escribir se devuelve a 1 bit
            im = lienzos[clave][0] = im.convert("L")
        r, g, b = int(tinta[0:2], 16), int(tinta[2:4], 16), int(tinta[4:6], 16)
        color = (r, g, b) if im.mode == "RGB" else (r * 299 + g * 587 + b * 114) // 1000
        ImageDraw.Draw(im).polygon([(u * im.width, (1 - v) * im.height) for u, v in esquinas], fill=color)
        tocada = True
    return tocada


def _escribir_imagenes(pdf, xobjetos, nombres: dict, lienzos: dict) -> int:
    hechas = 0
    for clave, (im, original, modo) in lienzos.items():
        if modo == "1":
            im = im.point(lambda v: 255 if v > 127 else 0).convert("1")
        comun = dict(Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=im.width, Height=im.height)
        if im.mode == "1":
            nuevo = pikepdf.Stream(pdf, im.tobytes(), ColorSpace=pikepdf.Name.DeviceGray, BitsPerComponent=1, **comun)
        else:
            espacio = pikepdf.Name.DeviceGray if im.mode == "L" else pikepdf.Name.DeviceRGB
            if str(original.get("/Filter", "")) == "/DCTDecode":
                salida = io.BytesIO()
                im.save(salida, "JPEG", quality=90)
                nuevo = pikepdf.Stream(pdf, salida.getvalue(), ColorSpace=espacio, BitsPerComponent=8,
                                       Filter=pikepdf.Name.DCTDecode, **comun)
            else:
                nuevo = pikepdf.Stream(pdf, im.tobytes(), ColorSpace=espacio, BitsPerComponent=8, **comun)
        for nombre in nombres.get(clave, ()):
            xobjetos[nombre] = nuevo
            hechas += 1
    return hechas


def bajo_las_tapas(pdf: pikepdf.Pdf, page: pikepdf.Page, tapas: list[tuple[float, float, float, float, str]],
                   recursos) -> tuple[int, int]:
    """Quita las letras y pinta las imágenes que quedan bajo las `tapas` (x0, y0, x1, y1, color),
    dadas en el espacio del PDF. `recursos` es el diccionario de recursos propio de la página.
    Devuelve (letras borradas, imágenes pintadas)."""
    if not tapas:
        return 0, 0
    fuentes_pdf = recursos.get("/Font") or {}
    xobjetos = recursos.get("/XObject")
    fuentes: dict[str, _Fuente] = {}
    instrucciones = pikepdf.parse_content_stream(page)
    salida = []
    pila: list[_Estado] = []
    e = _Estado()
    tm = tlm = IDENTIDAD
    borradas = 0
    lienzos: dict = {}
    nombres: dict = {}
    Op = pikepdf.Operator

    def mostrar(elementos) -> list | None:
        """Devuelve los elementos de un TJ sin las letras tapadas, o None si no hay que cambiar nada."""
        nonlocal tm, borradas
        f = e.fuente
        if f is None or not f.ok or e.cuerpo == 0:
            return None
        nuevo: list = []
        actual = bytearray()
        cambio = False

        def desplazar(n: float) -> None:
            if nuevo and not isinstance(nuevo[-1], pikepdf.String):
                nuevo[-1] = float(nuevo[-1]) + n
            else:
                nuevo.append(n)

        for el in elementos:
            if not isinstance(el, pikepdf.String):
                n = float(el)
                if actual:
                    nuevo.append(pikepdf.String(bytes(actual)))
                    actual = bytearray()
                desplazar(n)
                tm = _por((1, 0, 0, 1, -n / 1000.0 * e.cuerpo * e.th, 0), tm)
                continue
            crudo = bytes(el)
            for i in range(0, len(crudo) - f.n_bytes + 1, f.n_bytes):
                trozo = crudo[i:i + f.n_bytes]
                codigo = int.from_bytes(trozo, "big")
                avance = (f.ancho(codigo) / 1000.0 * e.cuerpo + e.tc + (e.tw if f.n_bytes == 1 and codigo == 32 else 0.0)) * e.th
                cx, cy = _punto(_por(tm, e.ctm), avance / 2.0, e.ts + e.cuerpo * 0.3)
                if _dentro(cx, cy, tapas):
                    if actual:
                        nuevo.append(pikepdf.String(bytes(actual)))
                        actual = bytearray()
                    desplazar(-avance * 1000.0 / (e.cuerpo * e.th))
                    borradas += 1
                    cambio = True
                else:
                    actual += trozo
                tm = _por((1, 0, 0, 1, avance, 0), tm)
        if actual:
            nuevo.append(pikepdf.String(bytes(actual)))
        return nuevo if cambio else None

    for instruccion in instrucciones:
        if not hasattr(instruccion, "operator"):
            salida.append(instruccion)
            continue
        operandos, op = list(instruccion.operands), str(instruccion.operator)
        try:
            if op == "q":
                pila.append(e.copia())
            elif op == "Q":
                if pila:
                    e = pila.pop()
            elif op == "cm":
                e.ctm = _por(tuple(float(v) for v in operandos), e.ctm)
            elif op == "BT":
                tm = tlm = IDENTIDAD
            elif op == "Tf":
                nombre = str(operandos[0])
                if nombre not in fuentes:
                    fuentes[nombre] = _Fuente(fuentes_pdf[nombre]) if nombre in fuentes_pdf else None
                e.fuente, e.cuerpo = fuentes[nombre], float(operandos[1])
            elif op == "Tc":
                e.tc = float(operandos[0])
            elif op == "Tw":
                e.tw = float(operandos[0])
            elif op == "Tz":
                e.th = float(operandos[0]) / 100.0
            elif op == "TL":
                e.tl = float(operandos[0])
            elif op == "Ts":
                e.ts = float(operandos[0])
            elif op in ("Td", "TD"):
                tx, ty = float(operandos[0]), float(operandos[1])
                if op == "TD":
                    e.tl = -ty
                tm = tlm = _por((1, 0, 0, 1, tx, ty), tlm)
            elif op == "Tm":
                tm = tlm = tuple(float(v) for v in operandos)
            elif op == "T*":
                tm = tlm = _por((1, 0, 0, 1, 0, -e.tl), tlm)
            elif op in ("Tj", "TJ", "'", '"'):
                previas = []
                if op == '"':
                    e.tw, e.tc = float(operandos[0]), float(operandos[1])
                    previas = [([operandos[0]], Op("Tw")), ([operandos[1]], Op("Tc"))]
                if op in ("'", '"'):
                    tm = tlm = _por((1, 0, 0, 1, 0, -e.tl), tlm)
                    previas.append(([], Op("T*")))
                elementos = list(operandos[0]) if op == "TJ" else [operandos[-1]]
                nuevo = mostrar(elementos)
                if nuevo is not None:
                    salida.extend(previas)
                    if nuevo:
                        salida.append(([pikepdf.Array(nuevo)], Op("TJ")))
                    continue
            elif op == "Do" and xobjetos is not None:
                nombre = str(operandos[0])
                objeto = xobjetos.get(nombre)
                if objeto is not None and str(objeto.get("/Subtype")) == "/Image":
                    if _pintar_imagen(pdf, objeto, e.ctm, tapas, lienzos):
                        nombres.setdefault(objeto.objgen, set()).add(nombre)
        except Exception:  # noqa: BLE001 - una instrucción rara no debe impedir seguir con las demás
            pass
        salida.append(instruccion)

    pintadas = _escribir_imagenes(pdf, xobjetos, nombres, lienzos) if lienzos else 0
    if borradas:
        page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(salida))
    return borradas, pintadas
