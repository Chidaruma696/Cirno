"""La parte «lista» de la extracción: tablas distintas en un mismo tramo, secciones, celdas que
doblan línea, totales, tipos por columna y datos sueltos."""

from datetime import date

import pdfplumber
import pytest
from openpyxl import load_workbook

from cirno.extraccion import datos, exportar
from cirno.extraccion.analisis import analizar
from cirno.extraccion.tablas import analizar_pagina, comprobar_totales, componer
from cirno.extraccion.valores import con_unidad, tipar_columna


def _tablas(ruta):
    with pdfplumber.open(str(ruta)) as pdf:
        return componer([analizar_pagina(p, i) for i, p in enumerate(pdf.pages, start=1)])


def _fila(y, valores, xs):
    return [(x, y, v) for x, v in zip(xs, valores) if v]


def test_dos_tablas_seguidas_con_encabezados_distintos(hacer_pdf):
    resumen, kardex = (60, 200, 420), (60, 130, 220, 400, 470)
    t = [(60, 84, "Existencias al corte")]
    t += _fila(100, ("Clave", "Producto", "Existencia"), resumen)
    t += _fila(116, ("CAJHU", "Caja de huevo blanco", "168.9 kg"), resumen)
    t += _fila(132, ("6003", "Casillero de huevo", "48 pz"), resumen)
    t += _fila(148, ("AZU50", "Azucar estandar", "12 pz"), resumen)
    y = 170
    for seccion, folios in (("Caja de huevo blanco (CAJHU)", ("B-1", "B-2", "B-3")), ("Casillero de huevo (6003)", ("C-1", "C-2", "C-3"))):
        t.append((60, y, seccion))
        t += _fila(y + 16, ("Fecha", "Folio", "Concepto", "Sale", "Saldo"), kardex)
        for k, folio in enumerate(folios):
            t += _fila(y + 32 + 16 * k, (f"0{k + 1}/09/2026", folio, "Venta mostrador", f"{k + 1}.50", f"{90 - k}.00"), kardex)
        y += 32 + 16 * len(folios) + 6
    primera, segunda = _tablas(hacer_pdf("existencias.pdf", [{"textos": t}]))
    assert primera.titulo == "Existencias al corte" and primera.filas[0] == ["Clave", "Producto", "Existencia"]
    assert primera.n_filas == 4 and primera.filas[1] == ["CAJHU", "Caja de huevo blanco", "168.9 kg"]
    # La segunda es una sola tabla con sus dos secciones: el encabezado una vez y el título de cada sección como columna.
    assert segunda.filas[0] == ["Sección", "Fecha", "Folio", "Concepto", "Sale", "Saldo"]
    assert segunda.n_filas == 7 and [f[2] for f in segunda.filas[1:]] == ["B-1", "B-2", "B-3", "C-1", "C-2", "C-3"]
    assert {f[0] for f in segunda.filas[1:4]} == {"Caja de huevo blanco (CAJHU)"} and segunda.filas[6][0] == "Casillero de huevo (6003)"


def test_celdas_que_doblan_linea_se_juntan_con_su_fila(hacer_pdf):
    xs = (60, 140, 330, 420)
    t = _fila(100, ("Clave", "Producto", "Pendiente", "Pedido desde"), xs)
    y = 124
    for clave, (uno, dos), cantidad, (f1, f2) in (
            ("ACEGRA", ("Aceite grano", "de oro 20 L"), "4 pz", ("2026-09-", "10")),
            ("HARESP", ("Harina espiga", "fina 25 kg"), "30 pz", ("2026-09-", "09")),
            ("MAIPOZ", ("Maiz pozolero", "el pozolito"), "12 pz", ("2026-09-", "11"))):
        # celdas centradas: la primera línea del nombre va por encima de la clave y la segunda por debajo
        t += [(xs[1], y - 6, uno), (xs[3], y - 6, f1)]
        t += [(xs[0], y, clave), (xs[2], y, cantidad)]
        t += [(xs[1], y + 6, dos), (xs[3], y + 6, f2)]
        y += 30
    (tabla,) = _tablas(hacer_pdf("pendientes.pdf", [{"textos": t, "cuerpo": 9}]))
    assert tabla.filas == [["Clave", "Producto", "Pendiente", "Pedido desde"],
                           ["ACEGRA", "Aceite grano de oro 20 L", "4 pz", "2026-09-10"],
                           ["HARESP", "Harina espiga fina 25 kg", "30 pz", "2026-09-09"],
                           ["MAIPOZ", "Maiz pozolero el pozolito", "12 pz", "2026-09-11"]]


def test_una_fila_sin_clave_pero_con_importe_no_es_continuacion(hacer_pdf):
    xs = (60, 150, 330, 430)
    t = _fila(100, ("Fecha", "Concepto", "Cargo", "Abono"), xs)
    for k in range(4):
        t += _fila(116 + 32 * k, (f"0{k + 1}/08/2026", f"Compra {k}", f"{(k + 1) * 100}.00", ""), xs)
        t += _fila(132 + 32 * k, ("", "aplicacion", "", f"{(k + 1) * 10}.00"), xs)  # sin fecha, pero es un renglón de datos
    (tabla,) = _tablas(hacer_pdf("estado.pdf", [{"textos": t}]))
    assert tabla.n_filas == 9 and tabla.filas[2] == ["", "aplicacion", "", "10.00"]


def test_totales_que_cuadran_y_que_no():
    filas = [["Producto", "Kilos", "Importe"], ["A", "10.5 kg", "1,000.00"], ["B", "4.5 kg", "250.50"], ["Total", "15 kg", "1,250.50"]]
    assert [c for c, _ in comprobar_totales(filas)] == [True, True]
    filas[3][2] = "1,300.00"
    (kilos, importe) = comprobar_totales(filas)
    assert kilos[0] and not importe[0] and "1,300.00" in importe[1] and "1,250.50" in importe[1]
    assert comprobar_totales(filas[:3]) == []


def test_columna_con_unidades_codigos_y_decimales_a_la_europea():
    assert con_unidad("168.9 kg") == (168.9, "kg", 1) and con_unidad("48 pz") == (48.0, "pz", 0) and con_unidad("B-06075") is None
    pesos = tipar_columna(["168.9 kg", "48 kg", "", "1,250.25 kg"])
    assert [v for v, _ in pesos] == [168.9, 48.0, None, 1250.25] and pesos[0][1] == '#,##0.0 "kg"' and pesos[1][1] == '#,##0 "kg"'
    assert [v for v, _ in tipar_columna(["007", "12", "345"])] == ["007", "12", "345"]  # un código arrastra a los demás
    assert [v for v, _ in tipar_columna(["1.234,56", "89,10", "12,00"])] == [1234.56, 89.1, 12.0]
    assert [v for v, _ in tipar_columna(["1,234.56", "89.10"])] == [1234.56, 89.1]
    assert tipar_columna(["Venta", "12 cajas grandes", "31/01/2026"])[1:] == [("12 cajas grandes", None), (date(2026, 1, 31), "DD/MM/YYYY")]


def test_datos_sueltos_y_tipo_de_documento(hacer_pdf, tmp_path):
    t = [(60, 60, "COTIZACION"), (60, 90, "Cliente: Abarrotes La Esperanza"), (330, 90, "Folio: COT-0042"),
         (60, 106, "RFC: AEL010203AB1"), (330, 106, "Fecha: 15/10/2026"), (60, 122, "Correo: compras@laesperanza.mx"),
         (60, 138, "CLABE 002180700845102349 para transferencias"), (60, 154, "La entrega se hace en el domicilio del cliente: sin costo."),
         (330, 300, "Subtotal"), (430, 300, "$1,000.00"), (330, 316, "IVA 16%"), (430, 316, "$160.00"), (330, 332, "Total"), (430, 332, "$1,160.00")]
    xs = (60, 150, 330, 430)
    t += _fila(200, ("Clave", "Producto", "Cantidad", "Importe"), xs)
    for k in range(3):
        t += _fila(216 + 16 * k, (f"P-{k}", f"Producto {k}", str(k + 1), f"{(k + 1) * 100}.00"), xs)
    a = analizar(hacer_pdf("cotizacion.pdf", [{"textos": t}]))
    campos = {c.nombre: c.valor for c in a.campos}
    assert a.tipo == "Cotización" and a.resumen().startswith("Cotización · ")
    assert campos["Cliente"] == "Abarrotes La Esperanza" and campos["Folio"] == "COT-0042" and campos["RFC"] == "AEL010203AB1"
    assert campos["Fecha"] == "15/10/2026" and campos["Total"] == "$1,160.00" and campos["Subtotal"] == "$1,000.00"
    assert campos["CLABE"] == "002180700845102349" and campos["Correo"] == "compras@laesperanza.mx"
    assert not any("entrega" in c.nombre.lower() for c in a.campos)  # una frase con dos puntos no es un dato
    assert sum(1 for c in a.campos if c.valor == "AEL010203AB1") == 1  # el RFC no sale dos veces (etiqueta y patrón)

    libro = load_workbook(exportar.a_excel(a, tmp_path / "cot.xlsx"))
    assert libro.sheetnames[0] == "Tabla 1 (p1)" and "Datos" in libro.sheetnames
    filas = {f[0]: f[1] for f in libro["Datos"].iter_rows(min_row=2, values_only=True)}
    assert filas["Total"] == pytest.approx(1160.0) and filas["Fecha"].date() == date(2026, 10, 15) and filas["Folio"] == "COT-0042"


def test_clabe_con_digito_de_control():
    assert datos.clabe_valida("002180700845102349") and not datos.clabe_valida("002180700845102348")
    assert datos.tipo_documento(["Folio fiscal 1234 CFDI de ingreso"]) == "Factura (CFDI)" and datos.tipo_documento(["hola"]) == ""


def test_hoja_con_el_titulo_de_la_tabla_y_comprobaciones(hacer_pdf, tmp_path):
    xs = (60, 200, 330, 430)
    t = [(60, 84, "Ventas de octubre")] + _fila(100, ("Vendedor", "Zona", "Cajas", "Importe"), xs)
    for k, (nombre, cajas, importe) in enumerate((("Ana", "10", "1,000.00"), ("Luis", "5", "500.50"), ("Rosa", "7", "700.00"))):
        t += _fila(116 + 16 * k, (nombre, "Norte", cajas, importe), xs)
    t += _fila(164, ("Total", "", "22", "2,200.50"), xs)
    a = analizar(hacer_pdf("ventas.pdf", [{"textos": t}]))
    assert a.tablas[0].titulo == "Ventas de octubre" and [c for c, _ in a.tablas[0].comprobaciones] == [True, True]
    libro = load_workbook(exportar.a_excel(a, tmp_path / "ventas.xlsx"))
    assert libro.sheetnames == ["Ventas de octubre", "Comprobaciones"]
    assert [f[1] for f in libro["Comprobaciones"].iter_rows(min_row=2, values_only=True)] == ["Cuadra", "Cuadra"]
    assert libro["Ventas de octubre"]["D2"].value == 1000.0
