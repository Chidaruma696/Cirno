"""Encontrar las tablas de un PDF, tengan rayas o no.

Dos maneras, en este orden:

1. **Con rayas.** Si la tabla está dibujada (bordes de celda), pdfplumber la reconstruye a
   partir de las líneas; es lo más fiable.
2. **Por alineación.** Casi todos los informes de oficina no dibujan nada: son texto colocado
   en columnas. Ahí se buscan tramos de renglones seguidos que tengan varios trozos separados
   por huecos anchos. Dentro de un tramo, cada fila de encabezado (varios trozos, ninguno con
   cifras, y debajo una fila con cifras) empieza una tabla: si el encabezado se repite, es la
   misma tabla que sigue (otra página, otra sección); si es distinto, es otra tabla. Las
   columnas de cada tabla salen de los «ríos» en blanco que comparten casi todas sus filas.

Además: el renglón suelto que precede a un encabezado repetido es el título de su sección y
pasa a ser una columna; el renglón suelto que cabe en una sola columna es una celda que dobló
línea y se une a la de arriba; y si la tabla trae fila de totales, se comprueba la suma.

Lo segundo es una intuición, no una certeza: puede tomar por tabla un texto a dos columnas.
Por eso la ventana enseña cada tabla antes de exportarla y deja desmarcarla.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .valores import es_total, numero

MIN_FILAS = 3  # renglones con varios trozos para hablar de tabla
HUECO_COLUMNA = 0.8  # × alto del renglón: un hueco mayor separa dos trozos
SALTO_RENGLON = 3.2  # × alto del renglón: más separación vertical corta el tramo
TOLERANCIA_RIO = 0.12  # parte de los renglones que puede pisar un río (títulos que abarcan columnas)
ANCHO_RIO = 2  # puntos mínimos de un río
MISMO_ANCHO = 0.85  # solape de anchos para decir que dos tramos de páginas seguidas son la misma tabla
COLUMNA_SECCION = "Sección"


@dataclass
class Tabla:
    pagina: int  # primera página donde aparece, desde 1
    filas: list[list[str]]
    origen: str  # "rayas" | "alineación"
    bbox: tuple[float, float, float, float]
    paginas: list[int] = field(default_factory=list)  # todas las páginas que abarca
    titulo: str = ""  # el renglón que la encabeza, si lo hay
    comprobaciones: list[tuple[bool, str]] = field(default_factory=list)  # (cuadra, explicación) de sus totales

    def __post_init__(self) -> None:
        if not self.paginas:
            self.paginas = [self.pagina]

    @property
    def n_filas(self) -> int:
        return len(self.filas)

    @property
    def n_columnas(self) -> int:
        return max((len(f) for f in self.filas), default=0)

    @property
    def donde(self) -> str:
        if len(self.paginas) > 1:
            return f"páginas {self.paginas[0]}-{self.paginas[-1]}"
        return f"página {self.pagina}"


def _texto_filas(filas) -> list[list[str]]:
    """Cada celda en una línea de texto, y fuera las filas vacías. Las columnas no se tocan."""
    filas = [[" ".join((c or "").split()) for c in fila] for fila in filas]
    return [f for f in filas if any(f)]


def _limpiar(filas) -> list[list[str]]:
    """Como `_texto_filas`, igualando el ancho y quitando además las columnas vacías del todo."""
    filas = _texto_filas(filas)
    ancho = max((len(f) for f in filas), default=0)
    filas = [f + [""] * (ancho - len(f)) for f in filas]
    vivas = [j for j in range(ancho) if any(f[j] for f in filas)]
    return [[f[j] for j in vivas] for f in filas]


def _con_varias(filas: list[list[str]]) -> int:
    return sum(1 for f in filas if sum(1 for c in f if c) >= 2)


def comprobar_totales(filas: list[list[str]]) -> list[tuple[bool, str]]:
    """Para cada fila de totales, compara sus cifras con la suma de lo que tiene encima (desde el
    total anterior). Solo habla de las columnas donde hay algo que sumar."""
    salida: list[tuple[bool, str]] = []
    cabeza = filas[0] if filas else []
    desde = 1
    for i, fila in enumerate(filas):
        primera = next((c for c in fila if c), "")
        if i == 0 or not es_total(primera):
            continue
        for j, celda in enumerate(fila):
            dicho = numero(celda)
            if dicho is None or celda == primera:
                continue
            sumandos = [numero(f[j]) for f in filas[desde:i] if j < len(f)]
            sumandos = [v for v in sumandos if v is not None]
            if len(sumandos) < 2:
                continue
            suma = round(sum(sumandos), 4)
            nombre = cabeza[j] if j < len(cabeza) and cabeza[j] else f"columna {j + 1}"
            cuadra = abs(suma - dicho) <= max(0.011, abs(dicho) * 1e-6)
            salida.append((cuadra, f"{primera.strip()} de «{nombre}»: el PDF dice {dicho:,.2f} y las filas suman {suma:,.2f}"))
        desde = i + 1
    return salida


# ----------------------------------------------------------------------------- con rayas

def tablas_con_rayas(page, n_pagina: int) -> list[Tabla]:
    salida = []
    try:
        encontradas = page.find_tables()
    except Exception:  # noqa: BLE001 - un PDF raro no debe tumbar el análisis de la página
        return []
    for t in encontradas:
        try:
            filas = _limpiar(t.extract())
        except Exception:  # noqa: BLE001
            continue
        if len(filas) >= 2 and len(filas[0]) >= 2 and _con_varias(filas) >= 2:
            salida.append(Tabla(n_pagina, filas, "rayas", tuple(t.bbox)))
    return salida


def unir_continuaciones(tablas: list[Tabla]) -> list[Tabla]:
    """Una tabla dibujada que sigue en la página siguiente (la primera de esa página, con las
    mismas columnas) se junta con la anterior; el encabezado repetido se quita."""
    salida: list[Tabla] = []
    for t in tablas:
        previa = salida[-1] if salida else None
        sigue = (
            previa is not None
            and t.pagina == previa.paginas[-1] + 1
            and t.n_columnas == previa.n_columnas
            and not any(o.pagina == t.pagina and o is not t and o.bbox[1] < t.bbox[1] for o in tablas)
        )
        if sigue:
            filas = t.filas[1:] if t.filas and t.filas[0] == previa.filas[0] else t.filas
            previa.filas = previa.filas + filas
            previa.paginas = previa.paginas + [t.pagina]
        else:
            salida.append(Tabla(t.pagina, list(t.filas), t.origen, t.bbox, list(t.paginas)))
    for t in salida:
        t.comprobaciones = comprobar_totales(t.filas)
    return salida


# ----------------------------------------------------------------------------- por alineación

@dataclass
class _Renglon:
    palabras: list[dict]
    top: float
    bottom: float
    trozos: list[tuple[float, float]] = field(default_factory=list)
    pagina: int = 0

    @property
    def alto(self) -> float:
        return max(self.bottom - self.top, 1.0)

    @property
    def suelto(self) -> bool:
        return len(self.trozos) < 2

    def textos(self) -> list[str]:
        """El texto de cada trozo, de izquierda a derecha."""
        return [" ".join(w["text"] for w in self.palabras if w["x0"] >= a - 0.5 and w["x1"] <= b + 0.5) for a, b in self.trozos]

    def texto(self) -> str:
        return " ".join(w["text"] for w in self.palabras)


@dataclass
class Candidata:
    """Un tramo de renglones que puede contener tablas."""

    pagina: int
    bloque: list[_Renglon]
    titulo: str = ""  # el renglón suelto que tiene justo encima

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (min(w["x0"] for r in self.bloque for w in r.palabras), self.bloque[0].top,
                max(w["x1"] for r in self.bloque for w in r.palabras), self.bloque[-1].bottom)


def _renglones(palabras: list[dict]) -> list[_Renglon]:
    if not palabras:
        return []
    alto = median(max(w["bottom"] - w["top"], 1.0) for w in palabras)
    tolerancia = max(2.0, alto * 0.45)
    renglones: list[_Renglon] = []
    for w in sorted(palabras, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"])):
        centro = (w["top"] + w["bottom"]) / 2
        r = renglones[-1] if renglones else None
        if r is not None and abs(centro - (r.top + r.bottom) / 2) <= tolerancia:
            r.palabras.append(w)
            r.top, r.bottom = min(r.top, w["top"]), max(r.bottom, w["bottom"])
        else:
            renglones.append(_Renglon([w], w["top"], w["bottom"]))
    for r in renglones:
        r.palabras.sort(key=lambda w: w["x0"])
        hueco = HUECO_COLUMNA * median(max(w["bottom"] - w["top"], 1.0) for w in r.palabras)
        x0, x1 = r.palabras[0]["x0"], r.palabras[0]["x1"]
        for w in r.palabras[1:]:
            if w["x0"] - x1 > hueco:
                r.trozos.append((x0, x1))
                x0 = w["x0"]
            x1 = max(x1, w["x1"])
        r.trozos.append((x0, x1))
    return renglones


def _bloques(renglones: list[_Renglon]) -> list[tuple[int, list[_Renglon]]]:
    """Tramos de renglones seguidos con varios trozos, cada uno con el índice donde empieza. Un
    renglón de un solo trozo se tolera dentro (una celda que dobla línea, un subtítulo) si el
    tramo continúa después."""
    bloques: list[tuple[int, list[_Renglon]]] = []
    actual: list[_Renglon] = []
    inicio = 0
    sueltos = 0

    def cerrar() -> None:
        nonlocal actual, sueltos
        while actual and actual[-1].suelto:
            actual.pop()
        if sum(1 for r in actual if not r.suelto) >= MIN_FILAS:
            bloques.append((inicio, actual))
        actual, sueltos = [], 0

    for i, r in enumerate(renglones):
        if actual and r.top - actual[-1].bottom > SALTO_RENGLON * max(r.alto, actual[-1].alto):
            cerrar()
        if not r.suelto:
            if not actual:
                inicio = i
            actual.append(r)
            sueltos = 0
        elif actual:
            sueltos += 1
            if sueltos > 2:
                cerrar()
            else:
                actual.append(r)
    cerrar()
    return bloques


def candidatas(palabras: list[dict], n_pagina: int) -> list[Candidata]:
    renglones = _renglones(palabras)
    salida = []
    for inicio, bloque in _bloques(renglones):
        for r in bloque:
            r.pagina = n_pagina
        titulo = ""
        if inicio > 0:
            previo = renglones[inicio - 1]
            cerca = bloque[0].top - previo.bottom <= SALTO_RENGLON * max(previo.alto, bloque[0].alto)
            if previo.suelto and cerca and len(previo.texto()) <= 80:
                titulo = previo.texto()
        salida.append(Candidata(n_pagina, bloque, titulo))
    return salida


def _columnas(renglones: list[_Renglon]) -> list[tuple[float, float]]:
    """Los tramos de X que ocupan los renglones, separados por ríos en blanco.

    Una columna densa es un tramo que pisan más renglones que la tolerancia; lo demás es río. La
    tolerancia deja pasar el título que abarca dos columnas sin fundirlas. Dentro de un río puede
    quedar una columna rala (un dato en dos de cuarenta renglones): se reconoce porque es una isla
    con blanco de verdad a los dos lados, cosa que un título que cruza el río no tiene."""
    varios = [r for r in renglones if not r.suelto]
    if not varios:
        return []
    x_min = int(min(t[0] for r in varios for t in r.trozos))
    x_max = int(max(t[1] for r in varios for t in r.trozos)) + 1
    n = x_max - x_min + 1
    cobertura = [0] * n
    for r in varios:
        for a, b in r.trozos:
            for x in range(int(a) - x_min, min(int(b) - x_min + 1, n)):
                cobertura[x] += 1
    permitido = int(len(varios) * TOLERANCIA_RIO)

    def tramos(vale) -> list[tuple[int, int]]:
        """Tramos [a, b) de posiciones seguidas que cumplen `vale`; un corte menor que un río no separa."""
        salida: list[tuple[int, int]] = []
        for i in range(n):
            if not vale(cobertura[i]):
                continue
            if salida and i - salida[-1][1] < ANCHO_RIO:
                salida[-1] = (salida[-1][0], i + 1)
            else:
                salida.append((i, i + 1))
        return salida

    densas = tramos(lambda c: c > permitido)
    if permitido:
        for a, b in tramos(lambda c: c > 0):
            if not any(a < d1 and d0 < b for d0, d1 in densas):  # isla que no toca ninguna columna densa
                densas.append((a, b))
        densas.sort()
    return [(x_min + a, x_min + b) for a, b in densas]


def _columna_de(x: float, fronteras: list[float]) -> int:
    return sum(1 for f in fronteras if x > f)


def _celdas(r: _Renglon, n_columnas: int, fronteras: list[float]) -> list[str]:
    celdas: list[list[str]] = [[] for _ in range(n_columnas)]
    if r.suelto:  # entero en la columna donde empieza
        celdas[_columna_de(r.trozos[0][0] + 0.5, fronteras)] = [r.texto()]
    else:
        for w in r.palabras:
            celdas[_columna_de((w["x0"] + w["x1"]) / 2, fronteras)].append(w["text"])
    return [" ".join(c) for c in celdas]


def _filas_de(renglones: list[_Renglon], columnas: list[tuple[float, float]]) -> list[list[str]]:
    """Las filas de una tabla, juntando con su fila los renglones que son parte de celdas que
    doblaron línea. Una fila «de verdad» trae algo en la primera columna; un renglón sin eso, que
    ocupa pocas columnas y no trae una cifra donde la columna lleva cifras (eso sería una fila de
    datos propia), pertenece a la fila de verdad más cercana: la de arriba si el texto dobla
    hacia abajo, o la de abajo si las celdas están centradas y el texto empieza antes."""
    fronteras = [(columnas[i][1] + columnas[i + 1][0]) / 2 for i in range(len(columnas) - 1)]
    n = len(columnas)
    crudas = [_celdas(r, n, fronteras) for r in renglones]
    anclas = [i for i, (f, r) in enumerate(zip(crudas, renglones)) if f[0] and not r.suelto]
    if len(anclas) < 2:
        return crudas
    # Columnas donde una cifra es un dato y no un trozo de texto: las que llevan cifras en las filas
    # de verdad. Si en esas filas la columna va vacía, se mira en todos los renglones: un abono que
    # solo aparece en los renglones de detalle es todo cifras; una fecha partida en dos líneas, no.
    numerica = []
    for j in range(n):
        llenas = [crudas[i][j] for i in anclas if crudas[i][j]] or [f[j] for f in crudas if f[j]]
        numerica.append(bool(llenas) and sum(1 for c in llenas if numero(c) is not None) >= 0.7 * len(llenas))
    centro = [(r.top + r.bottom) / 2 for r in renglones]

    def pegados(a: int, b: int) -> bool:
        """Si de un renglón al otro no hay ningún salto mayor que una línea."""
        return all(renglones[k + 1].top - renglones[k].bottom <= 1.2 * max(renglones[k].alto, renglones[k + 1].alto)
                   for k in range(a, b))

    destino: dict[int, int] = {}
    es_ancla = set(anclas)
    for i, (r, fila) in enumerate(zip(renglones, crudas)):
        if i in es_ancla:
            continue
        ocupadas = [j for j, c in enumerate(fila) if c]
        cabe = not r.suelto or _columna_de(r.trozos[0][1] - 0.5, fronteras) == ocupadas[0]
        if not cabe or (fila[0] and not r.suelto) or len(ocupadas) > max(1, n // 2):
            continue
        if any(numerica[j] and numero(fila[j]) is not None for j in ocupadas):
            continue
        arriba = max((k for k in anclas if k < i), default=None)
        abajo = min((k for k in anclas if k > i), default=None)
        d_arriba = centro[i] - centro[arriba] if arriba is not None and pegados(arriba, i) else float("inf")
        d_abajo = centro[abajo] - centro[i] if abajo is not None and pegados(i, abajo) else float("inf")
        if d_abajo < 0.8 * d_arriba:
            destino[i] = abajo
        elif d_arriba != float("inf"):
            destino[i] = arriba

    filas: list[list[str]] = []
    for i, fila in enumerate(crudas):
        if i in destino:
            continue
        partes = sorted([i] + [k for k, d in destino.items() if d == i])
        filas.append([_pegar([crudas[k][j] for k in partes if crudas[k][j]]) for j in range(n)] if len(partes) > 1 else fila)
    return filas


def _pegar(partes: list[str]) -> str:
    """Los trozos de una celda que dobló línea, con un espacio entre ellos salvo que el corte
    cayera en un guion o una barra entre cifras («2026-09-» + «10» es una fecha, no dos cosas)."""
    texto = ""
    for parte in partes:
        junto = len(texto) >= 2 and texto[-1] in "-/" and texto[-2].isdigit() and parte[:1].isdigit()
        texto = parte if not texto else (texto + parte if junto else f"{texto} {parte}")
    return texto


def _parece_tabla(filas: list[list[str]]) -> bool:
    """Descarta el texto corrido a dos columnas: celdas larguísimas y sin apenas números."""
    if len(filas) < MIN_FILAS or len(filas[0]) < 2:
        return False
    con_varias = _con_varias(filas)
    if con_varias < MIN_FILAS or con_varias < 0.5 * len(filas):
        return False
    celdas = [c for f in filas for c in f if c]
    largas = sum(1 for c in celdas if len(c) > 60)
    con_cifras = sum(1 for c in celdas if any(ch.isdigit() for ch in c))
    return not (largas > 0.4 * len(celdas) and con_cifras < 0.15 * len(celdas))


def _misma_tabla(a: Candidata, b: Candidata) -> bool:
    """Dos tramos en páginas seguidas son la misma tabla si ocupan casi el mismo ancho de página."""
    a0, _, a1, _ = a.bbox
    b0, _, b1, _ = b.bbox
    comun = min(a1, b1) - max(a0, b0)
    total = max(a1, b1) - min(a0, b0)
    return total > 0 and comun / total >= MISMO_ANCHO


# ---- encabezados y secciones

def _tiene_cifras(r: _Renglon) -> bool:
    return any(ch.isdigit() for w in r.palabras for ch in w["text"])


def _clave_cabecera(r: _Renglon) -> tuple[str, ...]:
    return tuple(t.lower() for t in r.textos())


def _cabeceras(renglones: list[_Renglon]) -> set[int]:
    """Los renglones que son fila de encabezado: varios trozos cortos, ninguno con cifras, tan
    anchos y con casi tantos trozos como las filas de datos, y con una fila de datos debajo. Si
    casi nada tiene cifras (una lista de nombres), no se puede distinguir y no hay ninguno."""
    varios = [i for i, r in enumerate(renglones) if not r.suelto]
    datos = [renglones[i] for i in varios if _tiene_cifras(renglones[i])]
    if len(varios) < MIN_FILAS or len(datos) < 0.5 * len(varios):
        return set()
    trozos_tipicos = median(len(r.trozos) for r in datos)
    ancho_tipico = median(r.trozos[-1][1] - r.trozos[0][0] for r in datos)
    salida = set()
    for k, i in enumerate(varios[:-1]):
        r = renglones[i]
        if _tiene_cifras(r) or max(len(t) for t in r.textos()) > 32:
            continue
        if len(r.trozos) < max(2, 0.6 * trozos_tipicos) or r.trozos[-1][1] - r.trozos[0][0] < 0.5 * ancho_tipico:
            continue  # dos palabras sueltas: una celda que dobló línea, no un encabezado
        if _tiene_cifras(renglones[varios[k + 1]]):
            salida.add(i)
    return salida


@dataclass
class _Tramo:
    """Las filas que van bajo un mismo encabezado."""

    cabecera: _Renglon | None
    filas: list[_Renglon]
    seccion: str = ""  # el renglón suelto que venía justo encima del encabezado
    primero: bool = False  # si empieza el tramo de la página (para heredar su título)


def _tramos(renglones: list[_Renglon]) -> list[_Tramo]:
    cabeceras = _cabeceras(renglones)
    tramos: list[_Tramo] = [_Tramo(None, [], primero=True)]
    for i, r in enumerate(renglones):
        if i in cabeceras:
            seccion = []
            actual = tramos[-1]
            while actual.filas and actual.filas[-1].suelto and len(seccion) < 2:  # el título de la sección que empieza
                seccion.insert(0, actual.filas.pop().texto())
            tramos.append(_Tramo(r, [], " ".join(seccion), primero=(i == 0)))
        else:
            tramos[-1].filas.append(r)
    return [t for t in tramos if t.cabecera is not None or t.filas]


def _tabla_de(tramos: list[_Tramo], titulo: str) -> Tabla | None:
    """Una tabla con todos los tramos que comparten encabezado."""
    cabecera = tramos[0].cabecera
    renglones = ([cabecera] if cabecera else []) + [r for t in tramos for r in t.filas]
    if sum(1 for r in renglones if not r.suelto) < MIN_FILAS:
        return None
    columnas = _columnas(renglones)
    if len(columnas) < 2:
        return None
    con_secciones = len(tramos) > 1 and any(t.seccion for t in tramos)
    if con_secciones and not tramos[0].seccion and titulo:
        tramos[0].seccion, titulo = titulo, ""
    filas: list[list[str]] = []
    if cabecera:
        filas += [([COLUMNA_SECCION] if con_secciones else []) + f for f in _filas_de([cabecera], columnas)]
    for t in tramos:
        filas += [([t.seccion] if con_secciones else []) + f for f in _filas_de(t.filas, columnas)]
    filas = _limpiar(filas)
    if not _parece_tabla(filas):
        return None
    paginas = sorted({r.pagina for r in renglones})
    bbox = (min(w["x0"] for r in renglones for w in r.palabras), renglones[0].top,
            max(w["x1"] for r in renglones for w in r.palabras), renglones[0].bottom)
    if not con_secciones and tramos[0].seccion:
        titulo = tramos[0].seccion
    return Tabla(paginas[0], filas, "alineación", bbox, paginas, titulo=titulo, comprobaciones=comprobar_totales(filas))


def _resolver(grupo: list[Candidata]) -> list[Tabla]:
    """Las tablas de un tramo de página, o de varios tramos seguidos en páginas consecutivas."""
    tramos = _tramos([r for c in grupo for r in c.bloque])
    tablas: list[Tabla] = []
    i = 0
    while i < len(tramos):
        j = i + 1
        clave = _clave_cabecera(tramos[i].cabecera) if tramos[i].cabecera else None
        while clave is not None and j < len(tramos) and tramos[j].cabecera and _clave_cabecera(tramos[j].cabecera) == clave:
            j += 1
        tabla = _tabla_de(tramos[i:j], grupo[0].titulo if i == 0 and tramos[0].primero else "")
        if tabla:
            tablas.append(tabla)
        i = j
    return tablas


def tablas_por_alineacion(palabras: list[dict], n_pagina: int) -> list[Tabla]:
    """Las tablas sin rayas de una sola página (`componer` hace lo mismo para un documento entero)."""
    return [t for c in candidatas(palabras, n_pagina) for t in _resolver([c])]


# ----------------------------------------------------------------------------- página y documento

def _se_tocan(a, b, margen: float = 0.0) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] - margen <= b[3] and b[1] - margen <= a[3]


def analizar_pagina(page, n_pagina: int, palabras: list[dict] | None = None) -> tuple[list[Tabla], list[Candidata]]:
    """Lo que hay en una página: las tablas dibujadas y los tramos que pueden ser tabla sin rayas.

    Un recuadro dibujado de una o dos filas suele ser solo el encabezado de una tabla cuyo cuerpo
    va sin rayas: si toca un tramo alineado, manda el tramo (que ya trae esas filas dentro)."""
    if palabras is None:
        palabras = page.extract_words()
    rayadas = tablas_con_rayas(page, n_pagina)
    grandes = [t for t in rayadas if t.n_filas >= MIN_FILAS]
    chicas = [t for t in rayadas if t.n_filas < MIN_FILAS]

    def fuera(w: dict) -> bool:
        cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
        return not any(t.bbox[0] <= cx <= t.bbox[2] and t.bbox[1] <= cy <= t.bbox[3] for t in grandes)

    sueltas = candidatas([w for w in palabras if fuera(w)] if grandes else palabras, n_pagina)
    chicas = [t for t in chicas if not any(_se_tocan(t.bbox, c.bbox, margen=12.0) for c in sueltas)]
    return grandes + chicas, sueltas


def componer(paginas: list[tuple[list[Tabla], list[Candidata]]]) -> list[Tabla]:
    """Las tablas del documento, en orden de lectura, a partir de lo que dio `analizar_pagina`
    para cada página. El último tramo alineado de una página y el primero de la siguiente, si
    ocupan el mismo ancho, se resuelven juntos."""
    grupos: list[list[Candidata]] = []
    ultimo_tramo: Candidata | None = None  # el último tramo de la página anterior
    for _, sueltas in paginas:
        sueltas = sorted(sueltas, key=lambda c: c.bbox[1])
        for i, c in enumerate(sueltas):
            sigue = (i == 0 and ultimo_tramo is not None and ultimo_tramo.pagina == c.pagina - 1
                     and _misma_tabla(ultimo_tramo, c))
            if sigue:
                grupos[-1].append(c)
            else:
                grupos.append([c])
        ultimo_tramo = sueltas[-1] if sueltas else None

    alineadas = [t for grupo in grupos for t in _resolver(grupo)]
    rayadas = unir_continuaciones([t for dibujadas, _ in paginas for t in sorted(dibujadas, key=lambda t: t.bbox[1])])
    return sorted(rayadas + alineadas, key=lambda t: (t.pagina, t.bbox[1]))


def tablas_de_pagina(page, n_pagina: int, palabras: list[dict] | None = None) -> list[Tabla]:
    """Las tablas de una sola página, de arriba abajo."""
    return componer([analizar_pagina(page, n_pagina, palabras)])
