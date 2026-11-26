from datetime import date

import pytest
from openpyxl import Workbook, load_workbook

from cirno.formato import recetas
from cirno.formato.recetas import Accion, RecetaError, aplicar, buscar_recetas, entender, prever
from cirno.formato.rules import Rule
from cirno.formato.workbook import inspect, value_index

FILAS = [
    ("F-003", "Luis", "PENDIENTE", 300.0, date(2026, 10, 3), "A3"),
    ("F-001", "Ana", "PAGADO", 1500.5, date(2026, 10, 1), "A1"),
    ("F-002", "luis", "PAGADO", 200.0, date(2026, 10, 2), None),
    ("F-004", "Rosa", "CANCELADO", 50.0, date(2026, 10, 4), "A4"),
    ("F-001", "Ana", "PAGADO", 1500.5, date(2026, 10, 1), "A1"),
    ("F-005", "Ana", "PENDIENTE", 800.0, date(2026, 10, 5), "A5"),
]


@pytest.fixture
def libro(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Cobranza"
    ws.append(["Folio", "Cliente", "Estado", "Importe", "Fecha", "Factura"])
    for f in FILAS:
        ws.append(list(f))
    ruta = tmp_path / "cobranza.xlsx"
    wb.save(ruta)
    return ruta


def plan_de(libro, texto):
    info = inspect(libro, "Cobranza")
    plan = entender(texto, info, value_index(libro, info))
    prever(libro, info, plan)
    return plan


def hacer(libro, texto, tmp_path):
    plan = plan_de(libro, texto)
    assert not plan.notas, plan.notas
    salida = aplicar(libro, "Cobranza", plan.pasos, tmp_path / "salida.xlsx")
    return load_workbook(salida), plan


def columna(wb, letra, hoja="Cobranza"):
    return [c.value for c in wb[hoja][letra][1:] if c.value is not None]


def test_la_frase_del_usuario(libro, tmp_path):
    """«busca los valores iguales, agrúpalos y pinta de color los que sean…»: tres pasos de una frase."""
    plan = plan_de(libro, "busca los valores iguales de Cliente, agrúpalos y pinta de verde los que sean PAGADO")
    assert not plan.notas
    repetidos, agrupar, pagados = plan.pasos
    assert isinstance(repetidos, Rule) and repetidos.column == "Cliente" and repetidos.condition.op == "duplicate"
    assert isinstance(agrupar, Accion) and agrupar.receta == "agrupar" and agrupar.columna == "Cliente" and agrupar.alcance == "3 grupos"
    assert isinstance(pagados, Rule) and pagados.column == "Estado" and pagados.condition.value == "PAGADO"
    wb = load_workbook(aplicar(libro, "Cobranza", plan.pasos, tmp_path / "salida.xlsx"))
    assert [c.lower() for c in columna(wb, "B")] == ["ana", "ana", "ana", "luis", "luis", "rosa"]  # los iguales, juntos
    reglas = wb["Cobranza"].conditional_formatting
    assert sum(len(r.rules) for r in reglas) == 2  # y el formato condicional, vivo, sobre las filas ya agrupadas
    assert wb["Cobranza"]["A5"].border.top.style == "medium" and wb["Cobranza"]["A3"].border.top.style is None  # raya al cambiar de grupo


def test_ordenar(libro, tmp_path):
    wb, _ = hacer(libro, "ordena de mayor a menor Importe", tmp_path)
    assert columna(wb, "D") == [1500.5, 1500.5, 800.0, 300.0, 200.0, 50.0]
    assert columna(wb, "A")[2:] == ["F-005", "F-003", "F-002", "F-004"]  # la fila entera viaja junta
    wb, plan = hacer(libro, "ordena por Fecha", tmp_path)
    assert columna(wb, "A") == ["F-001", "F-001", "F-002", "F-003", "F-004", "F-005"] and plan.pasos[0].descripcion.endswith("de menor a mayor")


def test_quitar_repetidos_y_filtrar(libro, tmp_path):
    wb, plan = hacer(libro, "quita los repetidos de Folio", tmp_path)
    assert columna(wb, "A") == ["F-003", "F-001", "F-002", "F-004", "F-005"] and plan.pasos[0].alcance == "quita 1 de 6 filas"
    wb, plan = hacer(libro, "deja solo los PENDIENTE", tmp_path)
    assert columna(wb, "A") == ["F-003", "F-005"] and plan.pasos[0].alcance == "quedan 2 de 6 filas"
    wb, _ = hacer(libro, "quita las filas donde Importe sea menor de 250", tmp_path)
    assert columna(wb, "D") == [300.0, 1500.5, 1500.5, 800.0]
    wb, _ = hacer(libro, "elimina los que no tengan Factura", tmp_path)
    assert "F-002" not in columna(wb, "A") and len(columna(wb, "A")) == 5


def test_resumen_con_formulas_y_totales(libro, tmp_path):
    wb, plan = hacer(libro, "suma Importe por Estado y cuántos hay por Cliente; pon totales", tmp_path)
    assert [a.receta for a in plan.pasos] == ["resumen", "resumen", "totales"]
    r1, r2 = wb["Resumen"], wb["Resumen 2"]
    assert [c.value for c in r1["A"]] == ["Estado", "CANCELADO", "PAGADO", "PENDIENTE", "Total"]
    assert r1["B3"].value == "=SUMIF('Cobranza'!$C$2:$C$7,A3,'Cobranza'!$D$2:$D$7)" and r1["B5"].value == "=SUM(B2:B4)"
    assert r2["B1"].value == "Cuántos" and r2["B2"].value == "=COUNTIF('Cobranza'!$B$2:$B$7,A2)"
    assert [c.value for c in r2["A"]][1:4] == ["Ana", "Luis", "Rosa"]  # «Luis» y «luis» son el mismo grupo
    ws = wb["Cobranza"]
    assert ws["D8"].value == "=SUM(D2:D7)" and ws["D8"].font.bold and ws["A8"].value == "Total"


def test_columna_calculada_texto_formato_y_filtros(libro, tmp_path):
    wb, plan = hacer(libro, "añade Importe con IVA; calcula Importe por 0.5 llamada Mitad; pon en mayúsculas Cliente; "
                     "Importe como moneda; pon filtros", tmp_path)
    ws = wb["Cobranza"]
    assert [a.receta for a in plan.pasos] == ["columna", "columna", "texto", "formato_numero", "filtros"]
    assert ws["G1"].value == "Importe con IVA" and ws["G2"].value == "=D2*1.16" and ws["H1"].value == "Mitad" and ws["H3"].value == "=D3*0.5"
    assert columna(wb, "B") == ["LUIS", "ANA", "LUIS", "ROSA", "ANA", "ANA"]
    assert ws["D2"].number_format == '"$"#,##0.00' and ws.auto_filter.ref == "A1:H7" and ws.freeze_panes == "A2"


def test_buscar_y_vacios_sin_decir_color(libro):
    plan = plan_de(libro, "busca rosa; marca los vacíos de Factura")
    busca, vacios = plan.pasos
    assert busca.column == "Cliente" and busca.condition.op == "contains" and busca.style.fill
    assert vacios.column == "Factura" and vacios.condition.op == "empty"


def test_lo_que_no_entiende_lo_dice_y_propone(libro):
    plan = plan_de(libro, "hazme un pastel; ordena")
    assert len(plan.notas) == 2 and not plan.pasos
    assert "pastel" in plan.notas[0] and "por qué columna ordenar" in plan.notas[1]
    plan = plan_de(libro, "pinta de rojo los PENDIENTE y luego ordénalo por Importe")
    assert [type(p).__name__ for p in plan.pasos] == ["Rule", "Accion"] and plan.pasos[1].columna == "Importe"


def test_el_recetario_se_puede_buscar():
    assert buscar_recetas("")[0].clave == "ordenar" and len(buscar_recetas("")) == len(recetas.CATALOGO)
    assert buscar_recetas("duplicados")[0].clave in ("quitar_repetidos", "repetidos")
    assert buscar_recetas("quiero sumar por cliente")[0].clave in ("resumen", "totales")
    assert buscar_recetas("moneda")[0].clave == "formato_numero"
    assert buscar_recetas("xyzzy") == []


def test_no_ordena_si_hay_formulas_ni_escribe_sobre_el_original(libro, tmp_path):
    wb = load_workbook(libro)
    wb["Cobranza"]["D3"] = "=D2*2"
    wb.save(libro)
    plan = plan_de(libro, "ordena por Folio")
    with pytest.raises(RecetaError):
        aplicar(libro, "Cobranza", plan.pasos, tmp_path / "x.xlsx")
    with pytest.raises(RecetaError):
        aplicar(libro, "Cobranza", plan.pasos, libro)
    assert not list(tmp_path.glob("*cirno-tmp*"))  # y no deja archivos temporales


def test_resumen_de_solo_una_parte(libro, tmp_path):
    wb, plan = hacer(libro, "quiero ver cuántos pendientes hay por cliente y el máximo de Importe por Estado", tmp_path)
    assert plan.pasos[0].opciones["solo"] == ("Estado", "pendiente") and "solo donde Estado es pendiente" in plan.pasos[0].descripcion
    assert wb["Resumen"]["B2"].value == "=COUNTIFS('Cobranza'!$B$2:$B$7,A2,'Cobranza'!$C$2:$C$7,\"pendiente\")"
    assert wb["Resumen 2"]["B2"].value == "=_xlfn.MAXIFS('Cobranza'!$D$2:$D$7,'Cobranza'!$C$2:$C$7,A2)"
