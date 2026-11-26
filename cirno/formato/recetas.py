"""El recetario: lo que Cirno sabe hacerle a una hoja de Excel además de pintarla.

Cada receta tiene un título, una descripción, ejemplos y las palabras por las que se la
reconoce. La orden del usuario se parte en frases; la que trae un color o un estilo va al
intérprete de formato (`parser`), y las demás se casan con el recetario: «ordena por fecha»,
«agrúpalos», «quita los repetidos», «suma el importe por cliente»… Lo que no casa con nada no se
adivina: se dice, y se proponen las recetas que más se le parecen.

Todo se aplica sobre una copia, en este orden: primero lo que cambia las filas (quitar, dejar,
ordenar, agrupar, columnas nuevas), luego el formato condicional, y al final lo que se apoya en
cómo quedó (totales, hoja de resumen con fórmulas, formatos de número, filtros).
"""

from __future__ import annotations

import re
import shutil
from copy import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import workbook
from .parser import SpanishParser, normalize, parse_number
from .rules import PALETTE, Condition, Rule, Style


class RecetaError(ValueError):
    """La receta no se puede aplicar a esta hoja, con un motivo que se le enseña al usuario."""


@dataclass(frozen=True)
class Receta:
    clave: str
    titulo: str
    descripcion: str
    ejemplos: tuple[str, ...]
    palabras: tuple[str, ...]  # raíces y frases, sin tildes, por las que se la busca
    fase: int = 1  # 1: cambia las filas · 2: pinta · 3: se apoya en cómo quedó la hoja


@dataclass
class Accion:
    receta: str
    descripcion: str
    columna: str | None = None
    opciones: dict = field(default_factory=dict)
    enabled: bool = True
    alcance: str = ""  # lo que haría ahora mismo («quitaría 12 filas»), para la vista previa


@dataclass
class Plan:
    pasos: list = field(default_factory=list)  # Rule (pintar) y Accion (recetas), en el orden en que se dijeron
    notas: list[str] = field(default_factory=list)

    @property
    def reglas(self) -> list[Rule]:
        return [p for p in self.pasos if isinstance(p, Rule)]

    @property
    def acciones(self) -> list[Accion]:
        return [p for p in self.pasos if isinstance(p, Accion)]


CATALOGO: tuple[Receta, ...] = (
    Receta("ordenar", "Ordenar por una columna", "Reordena las filas según una columna: de menor a mayor, de mayor a menor, alfabéticamente o por fecha.",
           ("ordena por Fecha", "ordena de mayor a menor Importe", "acomoda alfabéticamente por Cliente"),
           ("orden", "acomod", "clasific", "mayor a menor", "menor a mayor", "alfabet", "ascend", "descend", "mas reciente", "mas antigu")),
    Receta("agrupar", "Agrupar los iguales", "Junta las filas que tienen el mismo valor en una columna y separa cada grupo con una raya.",
           ("agrupa por Cliente", "junta los iguales de Estado", "agrúpalos"),
           ("agrup", "junt", "reun", "iguales juntos", "por grupo")),
    Receta("quitar_repetidos", "Quitar los repetidos", "Deja una sola fila de cada valor repetido en una columna (o de cada fila idéntica) y borra las demás.",
           ("quita los repetidos de Folio", "elimina los duplicados", "sin repetidos"),
           ("quit", "elimin", "borr", "repet", "duplic", "sin repet")),
    Receta("dejar", "Dejar solo unas filas", "Conserva las filas que cumplen una condición y borra las demás.",
           ("deja solo los PENDIENTE", "quédate con Importe mayor de 1000", "filtra Estado PAGADO"),
           ("deja solo", "dejame solo", "quedate con", "solo quiero", "conserv", "filtra")),
    Receta("quitar_filas", "Quitar unas filas", "Borra las filas que cumplen una condición.",
           ("quita las filas donde Estado sea CANCELADO", "elimina los que no tengan Factura", "borra las filas con Importe menor de 10"),
           ("quita las filas", "elimina las filas", "borra las filas", "quita los que", "elimina los que", "quita las que", "borra los que")),
    Receta("columna", "Columna calculada", "Añade una columna con una fórmula por fila: una columna por otra, por un número, el IVA…",
           ("nueva columna Cantidad por Precio", "añade Importe con IVA", "calcula Cargo menos Abono llamada Saldo"),
           ("nueva columna", "anad", "agreg", "calcul", "multiplic", "con iva", "iva de", "rest", "divid")),
    Receta("texto", "Arreglar el texto", "Pasa una columna a mayúsculas, minúsculas o nombre propio, o le quita los espacios de sobra.",
           ("pon en mayúsculas Cliente", "Nombre en nombre propio", "quita los espacios de sobra de Clave"),
           ("mayuscul", "minuscul", "nombre propio", "espacios")),
    Receta("repetidos", "Marcar los repetidos", "Resalta los valores que aparecen más de una vez en una columna.",
           ("busca los valores iguales de Folio", "marca los repetidos de Cliente", "resalta duplicados"),
           ("igual", "repet", "duplic"), fase=2),
    Receta("vacios", "Marcar los vacíos", "Resalta las celdas sin dato de una columna.",
           ("marca los vacíos de Factura", "resalta lo que esté en blanco"),
           ("vaci", "en blanco", "sin dato"), fase=2),
    Receta("buscar", "Buscar un texto", "Resalta todas las celdas donde aparece un texto, en cualquier columna.",
           ("busca vocho", "encuentra Atotonilco", "dónde dice cancelado"),
           ("busc", "encuentr", "localiz", "donde dice", "donde esta"), fase=2),
    Receta("resumen", "Resumen por grupos", "Crea una hoja «Resumen» con fórmulas (SUMAR.SI, CONTAR.SI…) que suman, cuentan o promedian una columna por cada valor de otra.",
           ("suma Importe por Cliente", "cuántos hay por Estado", "promedio de Kilos por Sucursal"),
           ("por cada", "resum", "tabla dinamica", "sum", "total", "cuant", "cuent", "promedi", "maxim", "minim"), fase=3),
    Receta("totales", "Fila de totales", "Añade al final una fila con la suma (o el promedio, el máximo, el mínimo, la cuenta) de las columnas con números.",
           ("suma la columna Importe", "pon totales", "promedio de Kilos"),
           ("sum", "total", "promedi", "maxim", "minim", "cuent"), fase=3),
    Receta("formato_numero", "Formato de número", "Enseña una columna como moneda, con decimales, como porcentaje, con separador de miles o como fecha.",
           ("Importe como moneda", "Kilos con 3 decimales", "Avance como porcentaje"),
           ("moned", "peso", "dinero", "decimal", "porcentaj", "miles", "como fecha", "formato de fecha"), fase=3),
    Receta("filtros", "Filtros y encabezado fijo", "Pone los filtros de Excel en el encabezado, lo deja fijo al desplazarse y ajusta el ancho de las columnas.",
           ("pon filtros", "congela el encabezado", "ajusta el ancho de las columnas"),
           ("filtros", "autofiltro", "congel", "inmoviliz", "fija el encabezado", "ajusta", "autoajust", "ancho"), fase=3),
)
POR_CLAVE = {r.clave: r for r in CATALOGO}

_VERBOS = ("orden", "acomod", "clasific", "agrup", "junt", "reun", "sum", "total", "promedi", "cuent", "cuant", "quit", "elimin",
           "borr", "dej", "quedat", "conserv", "filtr", "busc", "encuentr", "localiz", "congel", "inmoviliz", "fij", "ajust",
           "autoajust", "anad", "agreg", "calcul", "nuev", "pon", "pint", "marc", "resalt", "colore", "conviert", "cambi",
           "multiplic", "rest", "divid", "mayuscul", "minuscul", "formate", "muestr", "resum", "sin repet", "dime", "dame",
           "saca", "haz", "quiero", "necesito", "maxim", "minim")
_RELLENO = {"de", "del", "la", "las", "el", "los", "en", "a", "al", "que", "con", "lo", "me", "y", "e", "por", "favor", "columna",
            "columnas", "valores", "valor", "datos", "dato", "todos", "todas", "todo", "toda", "un", "una", "unos", "unas", "hoja"}
_FUNCIONES = (("promedio", ("promedi", "media de", "en promedio")), ("max", ("maxim", "el mayor", "mas alto")),
              ("min", ("minim", "el menor", "mas bajo")), ("suma", ("sum", "total")), ("cuenta", ("cuant", "cuent", "conte", "numero de")))
_NOMBRE_FUNCION = {"suma": "Suma", "cuenta": "Cuenta", "promedio": "Promedio", "max": "Máximo", "min": "Mínimo"}
_EXCEL = {"suma": "SUM", "cuenta": "COUNTA", "promedio": "AVERAGE", "max": "MAX", "min": "MIN"}
_EXCEL_SI = {"suma": "SUMIF", "cuenta": "COUNTIF", "promedio": "AVERAGEIF"}
# MAXIFS y MINIFS son funciones «nuevas» (Excel 2019): en el archivo llevan el prefijo _xlfn. o Excel no las reconoce.
_EXCEL_SIS = {"suma": "SUMIFS", "promedio": "AVERAGEIFS", "max": "_xlfn.MAXIFS", "min": "_xlfn.MINIFS"}
_OPERADORES = ((r"\s(?:por|x|multiplicad[oa] por)\s|\s?\*\s?", "*", "×"), (r"\s(?:mas|sumad[oa] a)\s|\s?\+\s?", "+", "+"),
               (r"\s(?:menos|restad[oa] de)\s|\s-\s", "-", "−"), (r"\s(?:entre|dividid[oa] (?:entre|por))\s|\s?/\s?", "/", "÷"))


# ----------------------------------------------------------------------------- entender

def _palabras(norm: str) -> list[str]:
    return [w for w in re.split(r"[^\wñ]+", norm) if w]


def _tiene(norm: str, *raices: str) -> bool:
    """Si la frase trae alguna de esas raíces (al empezar una palabra) o frases."""
    palabras = _palabras(norm)
    return any(bool(re.search(r"(?<![\wñ])" + re.escape(r.strip()), norm)) if " " in r.strip() else any(w.startswith(r.strip()) for w in palabras)
               for r in raices)


def _columnas_en(parser: SpanishParser, norm: str) -> list[tuple[str, int, int]]:
    """Las cabeceras que se nombran en la frase, en el orden en que aparecen."""
    halladas: list[tuple[str, int, int]] = []
    for nh, h in parser._norm_headers:  # de la más larga a la más corta: «Importe total» antes que «Importe»
        if not nh:
            continue
        raiz = nh[:-2] if nh.endswith("es") and len(nh) > 4 else nh[:-1] if nh.endswith("s") and len(nh) > 3 else nh
        for m in re.finditer(rf"(?<![\wñ])(?:{re.escape(nh)}|{re.escape(raiz)})(?:e?s)?(?![\wñ])", norm):
            if not any(a < m.end() and m.start() < b for _, a, b in halladas):
                halladas.append((h, m.start(), m.end()))
    return sorted(halladas, key=lambda t: t[1])


def partir(texto: str, parser: SpanishParser) -> list[str]:
    """Las frases de la orden. Una coma o una «y» separan cuando lo que sigue empieza con un verbo
    de receta («…, agrúpalos y pinta de rojo…»); si no, son parte de la frase («entre 1 y 5»)."""
    trozos = re.split(r"[;\n]|(?<=[^\d])\.\s+|\s+y\s+luego\s+|\s+luego\s+|\s+y\s+despues\s+|\s+despues\s+|\s+y\s+tambien\s+|\s+ademas\s+",
                      texto, flags=re.IGNORECASE)
    frases: list[str] = []
    for trozo in trozos:
        if not trozo or not trozo.strip():
            continue
        inicio = 0
        for m in re.finditer(r",\s*(?:y\s+)?|\s+y\s+|\s+e\s+", trozo):
            resto = normalize(trozo[m.end():]).lstrip()
            primera = re.sub(r"^(?:(?:que|me|lo|los|las|le|el|la)\s+)+", "", resto).split(" ")[0] if resto else ""
            if trozo[inicio:m.start()].strip() and any(primera.startswith(v) for v in _VERBOS):
                frases.append(trozo[inicio:m.start()].strip())
                inicio = m.end()
        if trozo[inicio:].strip():
            frases.append(trozo[inicio:].strip())
    return frases


def _valor_nombrado(parser: SpanishParser, norm: str, cols, fuera: set[str]) -> tuple[str, str] | None:
    """Si la frase nombra un valor que está en una sola columna («pendientes» → Estado), esa
    columna y el valor. Sirve para resumir solo una parte: «cuántos pendientes hay por cliente»."""
    for palabra in _palabras(norm):
        if palabra in _RELLENO or len(palabra) < 3 or any(a <= norm.find(palabra) < b for _, a, b in cols):
            continue
        for candidata in (palabra, palabra[:-1] if palabra.endswith("s") else "", palabra[:-2] if palabra.endswith("es") else ""):
            if not candidata:
                continue
            donde = [c for c in parser.columns_for(candidata, "eq") if c not in fuera]
            if len(donde) == 1:
                return donde[0], candidata
    return None


def _funcion(norm: str) -> str:
    for nombre, raices in _FUNCIONES:
        if _tiene(norm, *raices):
            return nombre
    return "suma"


def _condicion(parser: SpanishParser, frase: str, quitar: str) -> Rule:
    """La condición de una frase de «deja solo…» o «quita las filas…», leída por el intérprete de formato."""
    # normalize conserva la longitud: las palabras de la orden se borran en las mismas posiciones
    # del texto original, para no perder las mayúsculas del valor («PENDIENTE»).
    limpia = re.sub(quitar, lambda m: " " * len(m.group(0)), normalize(frase))
    original = "".join(o if n != " " else " " for o, n in zip(frase, limpia))
    return parser.parse_clause("rojo " + original)


def _sin_estilo(regla: Rule) -> str:
    return regla.description.split(", en ")[0] if regla.description else regla.column


def _reconocer(frase: str, parser: SpanishParser, info, previa: str | None) -> Accion | Rule | list | None:
    """La receta de una frase sin colores, con sus datos; None si no casa con ninguna."""
    norm = normalize(frase)
    cols = _columnas_en(parser, norm)
    primera = cols[0][0] if cols else None
    quitar = _tiene(norm, "quit", "elimin", "borr", "sin repet")
    repetidos = _tiene(norm, "repet", "duplic") or (_tiene(norm, "igual") and not _tiene(norm, "igual a", "sea igual", "es igual"))

    if repetidos and quitar:
        col = primera or (previa if _tiene(norm, "esos", "esas", "de esa columna", "de ahi") else None)
        return Accion("quitar_repetidos", f"Quitar las filas con {col} repetido" if col else "Quitar las filas repetidas (idénticas)", col)
    if _tiene(norm, "agrup", "junt", "reun"):
        col = primera or previa
        if not col:
            raise ValueError("dime por qué columna agrupar")
        return Accion("agrupar", f"Agrupar las filas por {col}", col)
    if repetidos:
        col = primera or previa
        if not col:
            raise ValueError("dime en qué columna buscar los repetidos")
        relleno, letra = PALETTE["red"]
        regla = Rule(column=col, condition=Condition(op="duplicate"), style=Style(fill=relleno, font_color=letra), scope="cell")
        regla.description = f"Celdas de {col} repetidas, en rojo"
        return regla
    if _tiene(norm, "mayuscul", "minuscul", "nombre propio", "espacios"):
        modo = ("mayusculas" if _tiene(norm, "mayuscul") else "minusculas" if _tiene(norm, "minuscul")
                else "propio" if "nombre propio" in norm else "espacios")
        col = primera or previa
        if not col:
            raise ValueError("dime qué columna")
        nombre = {"mayusculas": "en mayúsculas", "minusculas": "en minúsculas", "propio": "en nombre propio", "espacios": "sin espacios de sobra"}[modo]
        return Accion("texto", f"Poner {col} {nombre}", col, {"modo": modo})
    if _tiene(norm, "deja solo", "dejame solo", "deja unicamente", "quedate con", "solo quiero", "conserv", "filtra ", "filtrame"):
        regla = _condicion(parser, frase, r"\b(?:dejame|deja|quedate|conserva|filtrame|filtra|quiero|solo|solamente|unicamente|nada mas)\b")
        return Accion("dejar", f"Dejar solo: {_sin_estilo(regla).lower()}", regla.column, {"regla": regla})
    if quitar and _tiene(norm, "fila", "renglon", "registro", "los que", "las que", "donde", "lo que"):
        regla = _condicion(parser, frase, r"\b(?:quita|quitame|elimina|eliminame|borra|borrame)\b")
        return Accion("quitar_filas", f"Quitar: {_sin_estilo(regla).lower()}", regla.column, {"regla": regla})
    if _tiene(norm, "filtros", "autofiltro", "congel", "inmoviliz", "fija el encabezado", "autoajust") or (_tiene(norm, "ajust") and _tiene(norm, "ancho", "column")):
        return Accion("filtros", "Poner filtros, fijar el encabezado y ajustar los anchos")
    if _tiene(norm, "moned", "pesos", "dinero", "decimal", "porcentaj", "miles", "como fecha", "formato de fecha"):
        destino = [c for c, _, _ in cols] or ([previa] if previa else [])
        if not destino:
            raise ValueError("dime qué columna")
        m = re.search(r"(\d)\s+decimal", norm)
        if _tiene(norm, "moned", "pesos", "dinero"):
            formato, nombre = '"$"#,##0.00', "como moneda"
        elif _tiene(norm, "porcentaj"):
            formato, nombre = "0.00%", "como porcentaje"
        elif _tiene(norm, "fecha"):
            formato, nombre = "DD/MM/YYYY", "como fecha"
        elif m:
            formato, nombre = "#,##0." + "0" * int(m.group(1)) if int(m.group(1)) else "#,##0", f"con {m.group(1)} decimales"
        else:
            formato, nombre = "#,##0", "con separador de miles"
        return [Accion("formato_numero", f"Mostrar {c} {nombre}", c, {"formato": formato}) for c in destino]
    # «Importe por Cliente» puede ser multiplicar o repartir por grupos: solo es una columna nueva si se pide una.
    if _tiene(norm, "nueva columna", "anad", "agreg", "calcul", "multiplic", "divid", "iva", "llamad", "que se llame"):
        calculada = _columna_calculada(norm, frase, cols)
        if calculada:
            return calculada
    if _tiene(norm, "orden", "acomod", "clasific", "mayor a menor", "menor a mayor", "alfabet", "ascend", "descend"):
        fechas = [c.header for c in info.columns if c.kind == "date"]
        col = primera or (fechas[0] if len(fechas) == 1 and _tiene(norm, "reciente", "antigu", "fecha", "nuevo", "viejo") else previa)
        if not col:
            raise ValueError("dime por qué columna ordenar")
        al_reves = _tiene(norm, "mayor a menor", "descend", "mas reciente", "mas alto", "z a la a", "ultimos primero", "mas nuevo")
        return Accion("ordenar", f"Ordenar por {col}, {'de mayor a menor' if al_reves else 'de menor a mayor'}", col, {"al_reves": al_reves})
    if _tiene(norm, "sum", "total", "cuant", "cuent", "promedi", "maxim", "minim", "resum", "por cada", "tabla dinamica"):
        funcion = _funcion(norm)
        por = None
        m = None
        for m in re.finditer(r"\bpor(?:\s+cada)?\s+", norm):
            pass
        if m:
            por = next((c for c, a, _ in cols if a >= m.end() - 1 and a - m.end() <= 12), None)
        if por is None and previa and _tiene(norm, "cada uno", "cada una", "de cada", "cada grupo", "por grupo", "cada cual"):
            por = previa
        if por:
            medida = next((c for c, _, _ in cols if c != por), None)
            if funcion != "cuenta" and medida is None:
                numericas = [c.header for c in info.columns if c.kind == "number" and c.header != por]
                if len(numericas) != 1:
                    raise ValueError("dime qué columna sumar por " + por)
                medida = numericas[0]
            nombre = f"{_NOMBRE_FUNCION[funcion]} de {medida} por {por}" if funcion != "cuenta" or medida else f"Cuántas filas hay por {por}"
            solo = _valor_nombrado(parser, norm, cols, {por, medida})
            if solo:
                nombre += f", solo donde {solo[0]} es {solo[1]}"
            return Accion("resumen", f"Hoja «Resumen»: {nombre[0].lower() + nombre[1:]}", por,
                          {"medida": medida, "funcion": funcion, "solo": solo})
        destino = [c for c, _, _ in cols] or [c.header for c in info.columns if c.kind == "number"]
        if not destino:
            raise ValueError("no hay columnas con números que sumar")
        return Accion("totales", f"Fila de {_NOMBRE_FUNCION[funcion].lower()} de " + ", ".join(destino), None, {"columnas": destino, "funcion": funcion})
    if _tiene(norm, "vaci", "en blanco", "sin dato"):
        destino = [c for c, _, _ in cols] or ([previa] if previa else [])
        if not destino:
            raise ValueError("dime en qué columna buscar los vacíos")
        relleno, letra = PALETTE["gray"]
        salida = []
        for c in destino:
            regla = Rule(column=c, condition=Condition(op="empty"), style=Style(fill=relleno, font_color=letra), scope="cell")
            regla.description = f"Celdas sin {c}, en gris"
            salida.append(regla)
        return salida
    if _tiene(norm, "busc", "encuentr", "localiz", "donde dice", "donde esta"):
        m = re.search(r"\b(?:buscame|busca|buscar|encuentra|encuentrame|localiza|donde dice|donde esta)\b", norm)
        resto = frase[m.end():] if m else frase
        valor = " ".join(w for w in resto.split() if normalize(w).strip(".,:«»\"'") not in _RELLENO).strip(" .,:«»\"'")
        if not valor:
            raise ValueError("dime qué texto buscar")
        donde = parser.columns_for(valor, "contains") or [c.header for c in info.columns if c.kind in ("text", "mixed")]
        if not donde:
            raise ValueError(f"«{valor}» no aparece en ninguna columna")
        relleno, letra = PALETTE["yellow"]
        salida = []
        for c in donde:
            regla = Rule(column=c, condition=Condition(op="contains", value=valor), style=Style(fill=relleno, font_color=letra), scope="cell")
            regla.description = f"Celdas de {c} que contienen «{valor}», en amarillo"
            salida.append(regla)
        return salida
    return None


def _columna_calculada(norm: str, frase: str, cols: list[tuple[str, int, int]]) -> Accion | None:
    if not cols:
        return None
    nombre = None
    m = re.search(r"\b(?:llamad[ao]|que se llame|con (?:el )?nombre|titulad[ao])\s+(.+)$", norm)
    if m:
        nombre = frase[m.start(1):].strip(" .«»\"'")
        norm = norm[:m.start()]
        cols = [c for c in cols if c[2] <= m.start()]
        if not cols:
            return None
    a = cols[0]
    if re.search(r"\biva de\b", norm[:a[1]]):
        return Accion("columna", f"Columna nueva «{nombre or 'IVA de ' + a[0]}» = {a[0]} × 0.16", a[0],
                      {"nombre": nombre or f"IVA de {a[0]}", "a": a[0], "op": "*", "b": 0.16})
    if re.search(r"\b(?:con|mas)\s+(?:el\s+)?iva\b", norm[a[2]:]):
        return Accion("columna", f"Columna nueva «{nombre or a[0] + ' con IVA'}» = {a[0]} × 1.16", a[0],
                      {"nombre": nombre or f"{a[0]} con IVA", "a": a[0], "op": "*", "b": 1.16})
    resto = norm[a[2]:]
    for patron, op, signo in _OPERADORES:
        m = re.match(patron, resto)
        if not m:
            continue
        despues = resto[m.end():]
        b: str | float | None = None
        siguiente = next((c for c in cols[1:] if c[1] - a[2] - m.end() <= 6), None)
        if siguiente:
            b = siguiente[0]
        else:
            numero = re.match(r"\s*(-?[\d.,]+(?:\s*(?:mil|millones|millon))?)\s*(%)?", despues)
            valor = parse_number(numero.group(1)) if numero else None
            if valor is not None:
                b = float(valor) / 100.0 if numero.group(2) else float(valor)
        if b is None:
            continue
        return Accion("columna", f"Columna nueva «{nombre or f'{a[0]} {signo} {b}'}» = {a[0]} {signo} {b}", a[0],
                      {"nombre": nombre or f"{a[0]} {signo} {b}", "a": a[0], "op": op, "b": b})
    return None


def buscar_recetas(texto: str, cuantas: int | None = None) -> list[Receta]:
    """Las recetas que más se parecen a lo escrito, mirando palabras clave, título, descripción y
    ejemplos. Sin texto, todas."""
    palabras = [w for w in _palabras(normalize(texto)) if w not in _RELLENO and len(w) > 2]
    if not palabras:
        return list(CATALOGO)
    puntuadas = []
    for r in CATALOGO:
        mar = normalize(" ".join((r.titulo, r.descripcion, *r.ejemplos)))
        puntos = 0.0
        for w in palabras:
            if any(w.startswith(p) or (len(w) >= 4 and p.startswith(w[:4])) for p in r.palabras if " " not in p):
                puntos += 3
            elif any(p in normalize(texto) for p in r.palabras if " " in p):
                puntos += 2
            elif w[:5] in mar:
                puntos += 1
        if puntos:
            puntuadas.append((puntos, r))
    puntuadas.sort(key=lambda t: -t[0])
    return [r for _, r in puntuadas][:cuantas]


def entender(texto: str, info, valores: dict | None = None) -> Plan:
    """La orden entera convertida en pasos: reglas de formato y acciones del recetario."""
    parser = SpanishParser([c.header for c in info.columns], values=valores)
    plan = Plan()
    previa: str | None = None
    for frase in partir(texto, parser):
        nuevos: list = []
        try:
            if parser._has_style(frase):
                leido = parser.parse(frase)
                nuevos, notas = list(leido.rules), list(leido.notes)
                plan.notas += notas
            else:
                hallado = _reconocer(frase, parser, info, previa)
                if hallado is None:
                    parecidas = buscar_recetas(frase, 2)
                    pista = (" ¿Quizá " + " o ".join(f"«{r.ejemplos[0]}»" for r in parecidas) + "?") if parecidas else \
                        " Mira «Ideas» para ver lo que sé hacer."
                    plan.notas.append(f"No entendí «{frase.strip()}».{pista}")
                else:
                    nuevos = hallado if isinstance(hallado, list) else [hallado]
        except ValueError as e:
            plan.notas.append(f"No entendí «{frase.strip()}»: {e}")
        for paso in nuevos:
            columna = paso.column if isinstance(paso, Rule) else paso.columna
            previa = columna or previa
        plan.pasos += nuevos
    if not plan.pasos and not plan.notas:
        plan.notas.append("No encontré ninguna orden. Ejemplo: «ordena por Fecha y pinta de rojo los PENDIENTE».")
    return plan


# ----------------------------------------------------------------------------- aplicar

def _clave_orden(v):
    """Vacíos al final; números y fechas antes que textos, cada cosa en su orden."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return (3, 0, "")
    if isinstance(v, bool):
        return (0, float(v), "")
    if isinstance(v, (int, float)):
        return (0, float(v), "")
    if isinstance(v, (datetime, date)):
        d = v if isinstance(v, datetime) else datetime(v.year, v.month, v.day)
        return (1, d.timestamp() if d.year > 1970 else float(d.toordinal()), "")
    return (2, 0, normalize(str(v)).strip())


def _texto_clave(v) -> str:
    return "" if v is None else normalize(str(v)).strip()


class _Hoja:
    """La hoja abierta para cambiarla, con sus valores ya calculados al lado (para ordenar y comparar)."""

    def __init__(self, ruta: Path, nombre: str) -> None:
        self.ruta = ruta
        self.libro = load_workbook(ruta)
        self.ws = self.libro[nombre]
        self.info = workbook.inspect(ruta, nombre)
        valores = load_workbook(ruta, read_only=True, data_only=True)
        try:
            self.valores = [list(f) for f in valores[nombre].iter_rows(min_row=self.info.first_row, max_row=self.info.last_row,
                                                                        values_only=True)]
        finally:
            valores.close()
        self.ancho = max(self.ws.max_column, max((c.index for c in self.info.columns), default=1))
        for f in self.valores:
            f.extend([None] * (self.ancho - len(f)))

    def col(self, cabecera: str) -> int:
        return self.info.column(cabecera).index

    def valor(self, fila: int, cabecera: str):
        return self.valores[fila][self.col(cabecera) - 1]

    def sin_formulas(self, que: str) -> None:
        for fila in self.ws.iter_rows(min_row=self.info.first_row, max_row=self.info.last_row, max_col=self.ancho):
            if any(isinstance(c.value, str) and c.value.startswith("=") for c in fila):
                raise RecetaError(f"La hoja tiene fórmulas entre los datos, y {que} las rompería. Pega los datos como valores y vuelve a intentarlo.")
        if any(r.min_row >= self.info.first_row for r in self.ws.merged_cells.ranges):
            raise RecetaError(f"La hoja tiene celdas combinadas entre los datos; no se puede {que} sin deshacerlas.")

    def reordenar(self, orden: list[int]) -> None:
        """Deja las filas de datos en ese orden (índices sobre las actuales); puede dejar fuera algunas."""
        self.sin_formulas("mover o quitar filas")
        ws, primera = self.ws, self.info.first_row
        celdas = [[(c.value, copy(c._style)) for c in fila]
                  for fila in ws.iter_rows(min_row=primera, max_row=self.info.last_row, max_col=self.ancho)]
        for k, origen in enumerate(orden):
            for j, (valor, estilo) in enumerate(celdas[origen], start=1):
                celda = ws.cell(row=primera + k, column=j)
                celda.value = valor
                celda._style = estilo
        sobran = len(celdas) - len(orden)
        if sobran > 0:
            ws.delete_rows(primera + len(orden), sobran)
        self.valores = [self.valores[i] for i in orden]
        self.info.last_row = primera + len(orden) - 1


def _aplicar_datos(h: _Hoja, a: Accion) -> None:
    n = len(h.valores)
    if a.receta in ("ordenar", "agrupar"):
        j = h.col(a.columna) - 1
        orden = sorted(range(n), key=lambda i: _clave_orden(h.valores[i][j]), reverse=bool(a.opciones.get("al_reves")))
        if a.opciones.get("al_reves"):  # los vacíos, al final también de mayor a menor
            orden = [i for i in orden if _clave_orden(h.valores[i][j])[0] != 3] + [i for i in orden if _clave_orden(h.valores[i][j])[0] == 3]
        h.reordenar(orden)
        if a.receta == "agrupar":
            raya = Side(style="medium", color="808080")
            previo = object()
            for k, fila in enumerate(h.valores):
                clave = _texto_clave(fila[j])
                if k and clave != previo:
                    for celda in h.ws[h.info.first_row + k][:h.ancho]:
                        b = copy(celda.border)
                        celda.border = Border(left=b.left, right=b.right, bottom=b.bottom, top=raya)
                previo = clave
    elif a.receta == "quitar_repetidos":
        j = h.col(a.columna) - 1 if a.columna else None
        vistos: set = set()
        orden = []
        for i, fila in enumerate(h.valores):
            clave = _texto_clave(fila[j]) if j is not None else tuple(_texto_clave(v) for v in fila)
            if (j is not None and not clave) or clave not in vistos:  # los vacíos no cuentan como repetidos
                orden.append(i)
            vistos.add(clave)
        h.reordenar(orden)
    elif a.receta in ("dejar", "quitar_filas"):
        regla: Rule = a.opciones["regla"]
        j = h.col(regla.column) - 1
        cuenta: dict[str, int] = {}
        for fila in h.valores:
            clave = _texto_clave(fila[j])
            if clave:
                cuenta[str(fila[j]).casefold()] = cuenta.get(str(fila[j]).casefold(), 0) + 1
        cumple = [workbook.matches(regla, fila[j], cuenta) for fila in h.valores]
        h.reordenar([i for i in range(n) if cumple[i] == (a.receta == "dejar")])
    elif a.receta == "texto":
        j = h.col(a.columna)
        cambio = {"mayusculas": str.upper, "minusculas": str.lower, "propio": str.title, "espacios": lambda t: " ".join(t.split())}[a.opciones["modo"]]
        for k in range(n):
            celda = h.ws.cell(row=h.info.first_row + k, column=j)
            if isinstance(celda.value, str) and not celda.value.startswith("="):
                celda.value = cambio(celda.value)
                h.valores[k][j - 1] = celda.value
    elif a.receta == "columna":
        nueva = max(c.index for c in h.info.columns) + 1
        ultima = h.ws.cell(row=h.info.header_row, column=nueva - 1)
        cabecera = h.ws.cell(row=h.info.header_row, column=nueva, value=a.opciones["nombre"])
        cabecera._style = copy(ultima._style)
        la = get_column_letter(h.col(a.opciones["a"]))
        b = a.opciones["b"]
        for k in range(n):
            fila = h.info.first_row + k
            derecha = f"{get_column_letter(h.col(b))}{fila}" if isinstance(b, str) else repr(float(b))
            h.ws.cell(row=fila, column=nueva, value=f"={la}{fila}{a.opciones['op']}{derecha}").number_format = "#,##0.00"
        h.ws.column_dimensions[get_column_letter(nueva)].width = max(12, len(a.opciones["nombre"]) + 2)


def _ref_hoja(nombre: str) -> str:
    return "'" + nombre.replace("'", "''") + "'!"


def _aplicar_final(libro, ws, info, a: Accion, valores: list[list]) -> None:
    primera, ultima = info.first_row, info.last_row
    negrita = Font(bold=True)
    if a.receta == "totales":
        fila = ultima + 1
        columnas = [info.column(c) for c in a.opciones["columnas"]]
        raya = Side(style="thin", color="000000")
        libre = next((j for j in range(1, max(c.index for c in info.columns) + 1) if j not in {c.index for c in columnas}), None)
        if libre:
            ws.cell(row=fila, column=libre, value=_NOMBRE_FUNCION[a.opciones["funcion"]] if a.opciones["funcion"] != "suma" else "Total").font = negrita
        for c in columnas:
            celda = ws.cell(row=fila, column=c.index, value=f"={_EXCEL[a.opciones['funcion']]}({c.letter}{primera}:{c.letter}{ultima})")
            celda.font = negrita
            celda.border = Border(top=raya)
            celda.number_format = ws.cell(row=ultima, column=c.index).number_format
    elif a.receta == "resumen":
        por = info.column(a.columna)
        medida = info.column(a.opciones["medida"]) if a.opciones.get("medida") else None
        funcion = a.opciones["funcion"]
        grupos: dict[str, object] = {}
        for fila in valores:
            v = fila[por.index - 1] if por.index - 1 < len(fila) else None
            if _texto_clave(v):
                grupos.setdefault(_texto_clave(v), v)
        nombre, k = "Resumen", 2
        while nombre in libro.sheetnames:
            nombre, k = f"Resumen {k}", k + 1
        hoja = libro.create_sheet(nombre)
        titulo = f"{_NOMBRE_FUNCION[funcion]} de {medida.header}" if medida and funcion != "cuenta" else "Cuántos"
        relleno = PatternFill("solid", fgColor="D9E1F2")
        for j, texto in enumerate((por.header, titulo), start=1):
            celda = hoja.cell(row=1, column=j, value=texto)
            celda.font, celda.fill = negrita, relleno
        ref = _ref_hoja(ws.title)
        rango_por = f"{ref}${por.letter}${primera}:${por.letter}${ultima}"
        rango_medida = f"{ref}${medida.letter}${primera}:${medida.letter}${ultima}" if medida else ""
        solo = a.opciones.get("solo")
        extra = ""
        if solo:  # una segunda condición: solo las filas donde otra columna vale algo
            cs = info.column(solo[0])
            texto = solo[1].replace('"', '""')
            extra = f',{ref}${cs.letter}${primera}:${cs.letter}${ultima},"{texto}"'
            titulo += f" ({solo[1]})"
            hoja.cell(row=1, column=2, value=titulo)
        for i, valor in enumerate(sorted(grupos.values(), key=_clave_orden), start=2):
            hoja.cell(row=i, column=1, value=valor)
            if funcion == "cuenta" or medida is None:
                formula = f"=COUNTIFS({rango_por},A{i}{extra})" if extra else f"=COUNTIF({rango_por},A{i})"
            elif funcion in ("max", "min") or extra:
                formula = f"={_EXCEL_SIS[funcion]}({rango_medida},{rango_por},A{i}{extra})"
            else:
                formula = f"={_EXCEL_SI[funcion]}({rango_por},A{i},{rango_medida})"
            celda = hoja.cell(row=i, column=2, value=formula)
            if medida and funcion != "cuenta":
                celda.number_format = ws.cell(row=primera, column=medida.index).number_format
        fin = len(grupos) + 1
        if funcion in ("suma", "cuenta") and grupos:
            hoja.cell(row=fin + 1, column=1, value="Total").font = negrita
            total = hoja.cell(row=fin + 1, column=2, value=f"=SUM(B2:B{fin})")
            total.font = negrita
            total.number_format = hoja.cell(row=2, column=2).number_format
        hoja.column_dimensions["A"].width = min(max(len(str(v)) for v in [por.header, *grupos.values()]) + 4, 50)
        hoja.column_dimensions["B"].width = max(16, len(titulo) + 4)
        hoja.freeze_panes = "A2"
    elif a.receta == "formato_numero":
        c = info.column(a.columna)
        for fila in range(primera, ultima + 1):
            ws.cell(row=fila, column=c.index).number_format = a.opciones["formato"]
    elif a.receta == "filtros":
        ultima_col = max(c.index for c in info.columns)
        ws.auto_filter.ref = f"A{info.header_row}:{get_column_letter(ultima_col)}{ultima}"
        ws.freeze_panes = ws.cell(row=primera, column=1)
        for c in info.columns:
            largo = max([len(c.header)] + [len(str(f[c.index - 1])) for f in valores[:2000] if c.index - 1 < len(f) and f[c.index - 1] is not None])
            ws.column_dimensions[c.letter].width = min(max(largo + 3, 9), 60)


def _valores(ruta: Path, info) -> list[list]:
    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        return [list(f) for f in libro[info.name].iter_rows(min_row=info.first_row, max_row=info.last_row, values_only=True)]
    finally:
        libro.close()


def prever(origen: Path, info, plan: Plan) -> None:
    """Rellena `alcance` de cada acción con lo que haría ahora mismo sobre la hoja."""
    valores = _valores(origen, info)
    n = len(valores)
    for a in plan.acciones:
        try:
            if a.receta == "quitar_repetidos":
                j = info.column(a.columna).index - 1 if a.columna else None
                vistos: set = set()
                quita = 0
                for fila in valores:
                    clave = _texto_clave(fila[j]) if j is not None else tuple(_texto_clave(v) for v in fila)
                    if clave in vistos and (j is None or clave):
                        quita += 1
                    vistos.add(clave)
                a.alcance = f"quita {quita} de {n} filas"
            elif a.receta in ("dejar", "quitar_filas"):
                regla = a.opciones["regla"]
                j = info.column(regla.column).index - 1
                cumplen = sum(1 for fila in valores if workbook.matches(regla, fila[j] if j < len(fila) else None, {}))
                a.alcance = f"quedan {cumplen if a.receta == 'dejar' else n - cumplen} de {n} filas"
            elif a.receta in ("agrupar", "resumen"):
                j = info.column(a.columna).index - 1
                grupos = len({_texto_clave(f[j]) for f in valores if j < len(f) and _texto_clave(f[j])})
                a.alcance = f"{grupos} grupos"
            elif a.receta in ("ordenar", "texto", "columna", "formato_numero"):
                a.alcance = f"{n} filas"
            elif a.receta == "totales":
                cuantas = len(a.opciones["columnas"])
                a.alcance = "1 columna" if cuantas == 1 else f"{cuantas} columnas"
        except Exception:  # noqa: BLE001 - la vista previa no debe impedir aplicar
            a.alcance = ""


def aplicar(origen: Path, hoja: str, pasos: list, destino: Path) -> Path:
    """Escribe en `destino` una copia de `origen` con los pasos activos aplicados. Nunca toca el original."""
    origen, destino = Path(origen), Path(destino)
    if destino.resolve() == origen.resolve():
        raise RecetaError("El destino tiene que ser un archivo distinto del original.")
    activos = [p for p in pasos if p.enabled]
    reglas = [p for p in activos if isinstance(p, Rule)]
    de_datos = [p for p in activos if isinstance(p, Accion) and POR_CLAVE[p.receta].fase == 1]
    finales = [p for p in activos if isinstance(p, Accion) and POR_CLAVE[p.receta].fase == 3]
    temporal = destino.with_name(destino.stem + ".cirno-tmp" + destino.suffix)
    try:
        base = origen
        if de_datos:
            shutil.copyfile(origen, temporal)
            h = _Hoja(temporal, hoja)
            try:
                for a in de_datos:
                    _aplicar_datos(h, a)
                    h.libro.save(temporal)
                    h.libro.close()
                    h = _Hoja(temporal, hoja)  # la forma de la hoja cambió: se vuelve a leer
            finally:
                h.libro.close()
            base = temporal
        info = workbook.inspect(base, hoja)
        if reglas:
            workbook.apply(base, info, reglas, destino)
        else:
            shutil.copyfile(base, destino)
        if finales:
            valores = _valores(destino, info)
            libro = load_workbook(destino)
            try:
                for a in finales:
                    _aplicar_final(libro, libro[hoja], info, a, valores)
                libro.save(destino)
            finally:
                libro.close()
    finally:
        temporal.unlink(missing_ok=True)
    return destino
