from datetime import date

import pdfplumber
import pytest
from openpyxl import load_workbook
from PIL import Image

from cirno.convertir import convertir
from cirno.extraccion import exportar
from cirno.extraccion.analisis import analizar
from cirno.extraccion.exportar import tipar
from cirno.extraccion.tablas import analizar_pagina, componer
from cirno.pdf.guardar import imagen_a_pdf

COLUMNAS = (60, 150, 330, 430)
CABECERA = ("Folio", "Producto", "Cantidad", "Importe")


def _fila(y, valores, xs=COLUMNAS):
    return [(x, y, v) for x, v in zip(xs, valores) if v]


def _informe(n_filas, desde=1, y0=120, titulo=True):
    textos = [(60, 60, "Informe de ventas de la sucursal")] if titulo else []
    textos += _fila(y0, CABECERA)
    for k in range(n_filas):
        n = desde + k
        textos += _fila(y0 + 16 * (k + 1), (f"A-{n:03d}", f"Producto numero {n}", str(n * 3), f"{n * 1250.5:,.2f}"))
    return {"textos": textos}


def _tablas(ruta):
    with pdfplumber.open(str(ruta)) as pdf:
        return componer([analizar_pagina(p, i) for i, p in enumerate(pdf.pages, start=1)])


def test_tabla_sin_rayas(hacer_pdf):
    (t,) = _tablas(hacer_pdf("informe.pdf", [_informe(8)]))
    assert t.origen == "alineación" and (t.n_filas, t.n_columnas) == (9, 4)
    assert t.filas[0] == list(CABECERA)
    assert t.filas[3] == ["A-003", "Producto numero 3", "9", "3,751.50"]


def test_parrafos_no_son_tabla(hacer_pdf):
    lineas = ["Este documento explica con detalle el procedimiento que sigue la oficina",
              "para recibir la mercancia y dejarla registrada en el sistema de almacen,",
              "y no contiene ninguna tabla aunque tenga bastantes renglones seguidos",
              "con palabras de longitudes distintas que no se alinean en columnas."]
    ruta = hacer_pdf("carta.pdf", [{"textos": [(72, 100 + 14 * i, t) for i, t in enumerate(lineas * 3)]}])
    assert _tablas(ruta) == []


def test_tabla_que_sigue_en_varias_paginas_sale_una_sola(hacer_pdf):
    ruta = hacer_pdf("largo.pdf", [_informe(30), _informe(30, desde=31, y0=60, titulo=False),
                                   _informe(5, desde=61, y0=60, titulo=False)])
    (t,) = _tablas(ruta)
    assert t.paginas == [1, 2, 3] and t.donde == "páginas 1-3"
    assert t.n_filas == 1 + 65 and t.filas.count(list(CABECERA)) == 1
    assert [f[0] for f in t.filas[1:]] == [f"A-{n:03d}" for n in range(1, 66)]


def test_columna_rala_no_se_pierde(hacer_pdf):
    xs = (60, 150, 300, 380, 470)
    textos = _fila(100, ("Fecha", "Concepto", "Entra", "Sale", "Saldo"), xs)
    for k in range(30):
        ajuste = "5" if k == 17 else ""  # una sola entrada en treinta renglones
        textos += _fila(116 + 16 * k, (f"{k + 1:02d}/09/2026", f"Venta {k}", ajuste, "1", str(100 - k)), xs)
    (t,) = _tablas(hacer_pdf("kardex.pdf", [{"textos": textos}]))
    assert t.n_columnas == 5 and t.filas[18] == ["18/09/2026", "Venta 17", "5", "1", "83"]


def test_tabla_con_rayas(hacer_pdf):
    xs, ys = (50, 150, 300, 400), (90, 110, 130, 150, 170)
    lineas = [(x, ys[0], x, ys[-1]) for x in xs] + [(xs[0], y, xs[-1], y) for y in ys]
    textos = []
    for i, fila in enumerate((("Clave", "Nombre", "Saldo"), ("1", "Uno", "10.00"), ("2", "Dos", "20.00"), ("3", "Tres", "30.00"))):
        textos += [(x + 4, ys[i] + 14, v) for x, v in zip(xs, fila)]
    (t,) = _tablas(hacer_pdf("rayas.pdf", [{"textos": textos, "lineas": lineas}]))
    assert t.origen == "rayas" and t.filas == [["Clave", "Nombre", "Saldo"], ["1", "Uno", "10.00"],
                                              ["2", "Dos", "20.00"], ["3", "Tres", "30.00"]]


@pytest.mark.parametrize("texto,valor,formato", [
    ("1,234.50", 1234.5, "num"), ("$ 12,000.00", 12000.0, "num"), ("25,000.42-", -25000.42, "num"),
    ("(150.00)", -150.0, "num"), ("-3", -3, "int"), ("42", 42, "int"), ("12.5%", 0.125, "pct"),
    ("31/01/2026", date(2026, 1, 31), "fecha"), ("2026-01-31", date(2026, 1, 31), "fecha"),
    ("007", "007", None), ("168.9 kg", "168.9 kg", None), ("B-06075", "B-06075", None),
    ("01/09", "01/09", None), ("31/02/2026", "31/02/2026", None), ("1234567890123456", "1234567890123456", None),
    ("", None, None),
])
def test_tipar(texto, valor, formato):
    assert tipar(texto) == (valor, formato)


def test_excel_de_tablas_lleva_tipos_y_encabezado(hacer_pdf, tmp_path):
    a = analizar(hacer_pdf("informe.pdf", [_informe(4)]))
    assert a.estado is None and a.resumen() == "1 tabla · 1 página"
    ws = load_workbook(exportar.a_excel(a, tmp_path / "salida.xlsx")).active
    assert ws.title == "Tabla 1 (p1)" and [c.value for c in ws[1]] == list(CABECERA)
    assert ws["A2"].value == "A-001" and ws["C3"].value == 6 and ws["D3"].value == pytest.approx(2501.0)
    assert ws["A1"].font.bold and ws.freeze_panes == "A2"


def test_sin_tablas_va_el_texto(hacer_pdf, tmp_path):
    ruta = hacer_pdf("nota.pdf", [{"textos": [(72, 100, "Hola"), (72, 120, "Adios")]}])
    res = convertir([ruta], tmp_path / "out")
    assert len(res.salidas) == 1 and len(res.avisos) == 1
    ws = load_workbook(res.salidas[0])["Texto"]
    assert [c.value for c in ws["B"]] == ["Texto", "Hola", "Adios"]


def test_imagenes_paginas_y_texto(hacer_pdf, tmp_path):
    foto = tmp_path / "foto.png"
    im = Image.new("RGB", (120, 80), "blue")
    im.paste("yellow", (0, 0, 60, 80))
    im.save(foto)
    ruta = imagen_a_pdf(foto, tmp_path / "escaneo.pdf")
    a = analizar(ruta)
    assert a.escaneado and len(a.imagenes) == 1 and (a.imagenes[0].ancho, a.imagenes[0].alto) == (120, 80)
    assert a.resumen() == "1 imagen · 1 página · escaneado, sin texto"

    res = convertir([ruta], tmp_path / "out", imagenes=True, paginas=True, formato="jpg", ppp=96)
    nombres = sorted(p.name for p in res.salidas)
    assert nombres == ["escaneo-imagen-01.jpg", "escaneo-pagina-001.jpg"]
    assert any("escaneo" in aviso for aviso in res.avisos)  # no hay datos para Excel y lo dice
    sacada = Image.open(next(p for p in res.salidas if "imagen" in p.name))
    assert sacada.size == (120, 80)
    r, g, b = sacada.getpixel((100, 40))
    assert b > 200 and r < 60

    con_texto = hacer_pdf("dos.pdf", [{"textos": [(72, 100, "Primera")]}, {"textos": [(72, 100, "Segunda")]}])
    contenido = exportar.texto(analizar(con_texto), tmp_path / "dos.txt").read_text(encoding="utf-8-sig")
    assert "Página 1" in contenido and "Primera" in contenido and "Segunda" in contenido
