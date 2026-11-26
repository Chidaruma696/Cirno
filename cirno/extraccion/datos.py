"""Los datos sueltos de un documento, los que no van en tabla: «Cliente: Fulano», «Folio:
A-123», el total de una factura, un RFC, una CLABE, un folio fiscal. Y una idea de qué clase
de documento es. Todo con reglas y patrones: nada de modelos ni de red."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .tablas import _renglones

MAX_CAMPOS = 200

_ETIQUETA_VALOR = re.compile(r"^(?P<k>[A-ZÁÉÍÓÚÑ#][^:]{1,34}?)\s*:\s+(?P<v>\S.{0,118})$")
_SOLO_ETIQUETA = re.compile(r"^(?P<k>[A-ZÁÉÍÓÚÑ#][^:]{1,34}?)\s*:$")
_IMPORTE = r"\(?-?\$?\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?\)?"
_LINEA_TOTAL = re.compile(
    r"(?i)^(?P<k>sub\s?-?total|i\.?v\.?a\.?(?:\s*\(?\d{1,2}\s?%\)?)?|total(?:\s+(?:a\s+pagar|general|neto|con\s+letra|factura|mxn|usd))?"
    r"|importe\s+total|descuentos?|retenci[oó]n(?:es)?(?:\s+\w+)?|saldo(?:\s+(?:final|anterior|actual|inicial|a\s+favor|pendiente))?"
    r"|anticipo|cambio|efectivo|propina)\s*:?\s*(?P<v>" + _IMPORTE + r")(?:\s*(?:mxn|usd|m\.?n\.?|pesos))?$")
_PATRONES = (
    ("Folio fiscal (UUID)", re.compile(r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")),
    ("CURP", re.compile(r"\b[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b")),
    ("RFC", re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{2}[0-9A]\b")),
    ("Correo", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("CLABE", re.compile(r"(?<!\d)\d{18}(?!\d)")),
    ("Teléfono", re.compile(r"(?<![\d-])(?:\+?52[\s-]?)?(?:\(?\d{2,3}\)?[\s-]?)\d{3,4}[\s-]?\d{4}(?![\d-])")),
    ("Página web", re.compile(r"\b(?:https?://|www\.)[^\s<>\"]{4,80}")),
)
_TIPOS = (
    ("Factura (CFDI)", (("cfdi",), ("folio fiscal",), ("factura", "rfc"))),
    ("Nota de crédito", (("nota de crédito",), ("nota de credito",))),
    ("Recibo de nómina", (("nómina", "percepciones"), ("nomina", "percepciones"), ("recibo de nómina",))),
    ("Estado de cuenta", (("estado de cuenta",),)),
    ("Cotización", (("cotización",), ("cotizacion",), ("presupuesto",))),
    ("Pedido u orden de compra", (("orden de compra",), ("pedido",))),
    ("Remisión", (("remisión",), ("remision",))),
    ("Currículum", (("currículum",), ("curriculum",), ("experiencia laboral",), ("experiencia profesional",), ("habilidades", "experiencia"))),
    ("Kardex o inventario", (("kardex",), ("kárdex",), ("existencia", "saldo"), ("inventario", "existencia"))),
    ("Contrato", (("contrato", "cláusula"), ("contrato", "clausula"), ("contrato", "las partes"))),
    ("Factura", (("factura",), ("invoice",))),
    ("Recibo", (("recibo",), ("comprobante de pago",))),
    ("Carta", (("a quien corresponda",), ("atentamente",), ("estimado",), ("estimada",))),
)


@dataclass
class Campo:
    nombre: str
    valor: str
    pagina: int
    origen: str  # "etiqueta": estaba escrito «Nombre: valor» · "patrón": se reconoció por su forma


def clabe_valida(cifras: str) -> bool:
    """La CLABE lleva un dígito de control: pesos 3, 7, 1 sobre las 17 primeras cifras."""
    if len(cifras) != 18 or not cifras.isdigit():
        return False
    suma = sum((int(c) * (3, 7, 1)[i % 3]) % 10 for i, c in enumerate(cifras[:17]))
    return (10 - suma % 10) % 10 == int(cifras[17])


def _etiqueta_buena(k: str) -> bool:
    k = k.strip()
    if len(k.split()) > 4 or sum(c.isdigit() for c in k) > 2 or any(c in k for c in ",;()"):
        return False
    return not re.fullmatch(r"\d{1,2}", k.split()[-1])  # «12:30» no es «12: 30»


def campos_de_pagina(palabras: list[dict], texto: str, n_pagina: int) -> list[Campo]:
    salida: list[Campo] = []
    for r in _renglones(palabras):
        trozos = [" ".join(w["text"] for w in r.palabras if w["x0"] >= a - 0.5 and w["x1"] <= b + 0.5) for a, b in r.trozos]
        linea = " ".join(trozos)
        m = _LINEA_TOTAL.match(linea)
        if m:
            salida.append(Campo(m.group("k").strip().capitalize(), m.group("v").strip(), n_pagina, "etiqueta"))
            continue
        i = 0
        while i < len(trozos):
            t = trozos[i].strip()
            m = _ETIQUETA_VALOR.match(t)
            if m and _etiqueta_buena(m.group("k")):
                salida.append(Campo(m.group("k").strip(), m.group("v").strip(), n_pagina, "etiqueta"))
            else:
                m = _SOLO_ETIQUETA.match(t)
                if m and _etiqueta_buena(m.group("k")) and i + 1 < len(trozos) and not trozos[i + 1].rstrip().endswith(":"):
                    salida.append(Campo(m.group("k").strip(), trozos[i + 1].strip(), n_pagina, "etiqueta"))
                    i += 1
            i += 1
    for nombre, rx in _PATRONES:
        for m in rx.finditer(texto):
            valor = m.group(0).strip().rstrip(".,;")
            if nombre == "CLABE" and not clabe_valida(valor):
                continue
            if nombre == "Teléfono" and len(re.sub(r"\D", "", valor)) not in (10, 12):
                continue
            if nombre == "RFC" and not (any(c.isdigit() for c in valor) and re.search(r"\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", valor)):
                continue
            salida.append(Campo(nombre, valor, n_pagina, "patrón"))
    return salida


def unir(campos: list[Campo]) -> list[Campo]:
    """Sin repetidos: el mismo valor una vez (gana el que venía con su etiqueta), en orden de aparición."""
    salida: list[Campo] = []
    vistos: set[tuple[str, str]] = set()
    valores: set[str] = set()
    for c in sorted(campos, key=lambda c: (c.origen != "etiqueta",)):
        clave = (c.nombre.lower(), c.valor.lower())
        if clave in vistos or (c.origen == "patrón" and any(c.valor.lower() in v for v in valores)):
            continue
        vistos.add(clave)
        valores.add(c.valor.lower())
        salida.append(c)
    salida.sort(key=lambda c: (c.pagina, c.origen != "etiqueta"))
    return salida[:MAX_CAMPOS]


def tipo_documento(textos: list[str]) -> str:
    """Qué parece el documento, por las palabras de sus dos primeras páginas. Cadena vacía si no se sabe."""
    texto = " ".join(textos[:2]).lower()
    for nombre, opciones in _TIPOS:
        if any(all(p in texto for p in grupo) for grupo in opciones):
            return nombre
    return ""
