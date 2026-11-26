"""Entender el valor de una celda de texto: número, porcentaje, fecha, cantidad con unidad…
Primero celda a celda y con mucha cautela (`tipar`), y luego mirando la columna entera
(`tipar_columna`), que es donde se ve si aquello son importes, códigos o pesos en kilos."""

from __future__ import annotations

import re
from datetime import date

FMT_NUM = "#,##0.00;[Red]-#,##0.00"
FMT_FECHA = "DD/MM/YYYY"
FMT_PCT = "0.00%"

_NUMERO = re.compile(r"^\(?[-+]?\s?\$?\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s?%?-?\)?$")
_EUROPEO = re.compile(r"^\(?[-+]?\s?[$€]?\s?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{1,2}\s?[€%]?-?\)?$")
_DECIMAL_PUNTO = re.compile(r"\.\d{1,2}\D*$")
_SOLO_CIFRAS = re.compile(r"^\d+$")
_CON_UNIDAD = re.compile(r"^(?P<n>\(?[-+]?\s?\$?\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?-?\)?)\s?(?P<u>[A-Za-zÁÉÍÓÚÑáéíóúñµ°²³]{1,6}\.?(?:/[A-Za-z]{1,4})?)$")
_FECHAS = (
    (re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$"), "dma"),
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), "amd"),
)
_TOTAL = re.compile(r"(?i)^\s*(?:gran\s+|sub\s?-?)?total(?:es)?\b|^\s*sumas?\b|^\s*importe\s+total\b")


def tipar(texto: str):
    """El valor de una celda como lo querría Excel: número, porcentaje o fecha cuando lo es sin
    ninguna duda, y texto en lo demás. Devuelve (valor, formato) con formato "num", "int",
    "pct", "fecha" o None."""
    t = texto.strip()
    if not t:
        return None, None
    for rx, orden in _FECHAS:
        m = rx.match(t)
        if m:
            a, b, c = (int(g) for g in m.groups())
            try:
                return (date(c, b, a) if orden == "dma" else date(a, b, c)), "fecha"
            except ValueError:
                return t, None
    if not _NUMERO.match(t):
        return t, None
    cifras = re.sub(r"[^\d.]", "", t)
    entero = cifras.split(".")[0]
    # Con ceros a la izquierda o muy largo no es una cantidad: es un código, un folio, una cuenta.
    if (len(entero) > 1 and entero.startswith("0")) or len(entero) > 15:
        return t, None
    negativo = t.startswith("(") or t.rstrip(")").endswith("-") or t.lstrip("($ ").startswith("-")
    valor = float(cifras)
    if negativo:
        valor = -valor
    if "%" in t:
        return valor / 100.0, "pct"
    if "." not in cifras and "," not in t and "$" not in t:
        return int(valor), "int"
    return valor, "num"


def con_unidad(texto: str) -> tuple[float, str, int] | None:
    """«168.9 kg» → (168.9, "kg", 1): el número, su unidad y cuántos decimales traía."""
    m = _CON_UNIDAD.match(texto.strip())
    if not m:
        return None
    valor, formato = tipar(m.group("n"))
    if formato not in ("num", "int"):
        return None
    decimales = len(m.group("n").rstrip(")-").split(".")[1]) if "." in m.group("n") else 0
    return float(valor), m.group("u"), decimales


def numero(texto: str) -> float | None:
    """El número que hay en la celda (aunque lleve unidad), o None."""
    valor, formato = tipar(texto)
    if formato in ("num", "int", "pct"):
        return float(valor)
    unidad = con_unidad(texto)
    return unidad[0] if unidad else None


def _europeo(texto: str):
    limpio = texto.strip().replace(".", "").replace(",", ".").replace("€", "")
    return tipar(limpio)


def tipar_columna(celdas: list[str]) -> list[tuple[object, str | None]]:
    """Las celdas de una columna (sin el encabezado) con su valor y su formato de número de
    Excel (o None). Decide con toda la columna a la vista:

    - Si alguna celda es un código con ceros a la izquierda, todas las de solo cifras son códigos
      y se quedan como texto (para no mezclar «007» con 12).
    - Si los decimales van con coma («1.234,56») y ninguno con punto, se leen a la europea.
    - Si casi todo son cantidades con unidad («168.9 kg», «48 pz»), se guardan como números con
      la unidad en el formato: se ven igual y se pueden sumar."""
    llenas = [c.strip() for c in celdas if c and c.strip()]
    codigos = any(len(c) > 1 and c.startswith("0") and _SOLO_CIFRAS.match(c) for c in llenas)
    europeas = sum(1 for c in llenas if _EUROPEO.match(c))
    a_la_europea = europeas >= 2 and not any(_DECIMAL_PUNTO.search(c) and _NUMERO.match(c) for c in llenas)
    con_u = sum(1 for c in llenas if tipar(c)[1] is None and con_unidad(c))
    numericas = sum(1 for c in llenas if tipar(c)[1] in ("num", "int"))
    usar_unidades = con_u >= 2 and (con_u + numericas) >= 0.6 * len(llenas)

    salida: list[tuple[object, str | None]] = []
    for celda in celdas:
        t = (celda or "").strip()
        if not t:
            salida.append((None, None))
            continue
        if codigos and _SOLO_CIFRAS.match(t):
            salida.append((t, None))
            continue
        valor, formato = _europeo(t) if a_la_europea and _EUROPEO.match(t) else tipar(t)
        if formato is None and usar_unidades:
            unidad = con_unidad(t)
            if unidad:
                cantidad, nombre, decimales = unidad
                ceros = "." + "0" * decimales if decimales else ""
                salida.append((cantidad, f'#,##0{ceros} "{nombre.replace(chr(34), "")}"'))
                continue
        salida.append((valor, {"num": FMT_NUM, "pct": FMT_PCT, "fecha": FMT_FECHA}.get(formato)))
    return salida


def es_total(texto: str) -> bool:
    return bool(_TOTAL.match(texto or ""))
