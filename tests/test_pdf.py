import pdfplumber
import pikepdf
import pytest
from PIL import Image

from cirno.pdf import render
from cirno.pdf.documento import Documento
from cirno.pdf.guardar import ErrorGuardar, dividir, guardar, imagen_a_pdf


def textos(ruta):
    # En una página girada el extractor devuelve las palabras en otro orden: se normaliza a «letras número».
    with pdfplumber.open(str(ruta)) as pdf:
        return [" ".join(sorted((p.extract_text() or "").split(), key=str.isdigit)) for p in pdf.pages]


def giros(ruta):
    with pikepdf.open(str(ruta)) as pdf:
        return [int(p.obj.get("/Rotate", 0)) % 360 for p in pdf.pages]


@pytest.fixture
def doc(pdf_numerado):
    a = render.abrir(pdf_numerado("a.pdf", 3, "a"))
    b = render.abrir(pdf_numerado("b.pdf", 2, "b"))
    d = Documento()
    d.agregar_fuente(a)
    d.agregar_fuente(b)
    yield d
    a.cerrar()
    b.cerrar()


def orden(d):
    return [f"{p.fuente.nombre[0]}{p.indice + 1}" for p in d.paginas]


def test_abrir_cuenta_paginas_y_tamanos(pdf_numerado):
    f = render.abrir(pdf_numerado("x.pdf", 4))
    assert f.n_paginas == 4 and f.tamanos[0] == pytest.approx((612, 792))
    im = render.pintar(f, 0, lado_max=200)
    assert max(im.size) == 200 and im.mode == "RGB"
    f.cerrar()


def test_abrir_algo_que_no_es_pdf(tmp_path):
    malo = tmp_path / "malo.pdf"
    malo.write_text("esto no es un pdf")
    with pytest.raises(render.PdfIlegible):
        render.abrir(malo)


def test_pdf_con_clave(pdf_numerado, tmp_path):
    cifrado = tmp_path / "cifrado.pdf"
    with pikepdf.open(str(pdf_numerado("claro.pdf", 2))) as pdf:
        pdf.save(str(cifrado), encryption=pikepdf.Encryption(owner="dueno", user="secreto"))
    with pytest.raises(render.ClaveNecesaria):
        render.abrir(cifrado)
    with pytest.raises(render.ClaveNecesaria):
        render.abrir(cifrado, clave="otra")
    f = render.abrir(cifrado, clave="secreto")
    d = Documento()
    d.agregar_fuente(f)
    salida = guardar(d.paginas, tmp_path / "abierto.pdf")
    assert textos(salida) == ["pagina 1", "pagina 2"]
    f.cerrar()


def test_mover_conserva_el_orden_entre_si(doc):
    assert orden(doc) == ["a1", "a2", "a3", "b1", "b2"]
    assert doc.mover([0, 2], 5) == [3, 4]
    assert orden(doc) == ["a2", "b1", "b2", "a1", "a3"]
    assert doc.mover([3, 4], 0) == [0, 1]
    assert orden(doc) == ["a1", "a3", "a2", "b1", "b2"]
    assert doc.mover([1], 3) == [2]  # delante de la fila 3 de la lista actual
    assert orden(doc) == ["a1", "a2", "a3", "b1", "b2"]


def test_mover_sin_cambio_no_ensucia_el_historial(doc):
    doc._deshacer.clear()
    doc.mover([1], 1)
    doc.mover([1], 2)
    assert not doc.puede_deshacer


def test_deshacer_y_rehacer(doc):
    doc.eliminar([0, 1])
    doc.rotar([0], 90)
    assert orden(doc) == ["a3", "b1", "b2"] and doc.paginas[0].rotacion == 90
    assert doc.deshacer() and doc.paginas[0].rotacion == 0
    assert doc.deshacer() and orden(doc) == ["a1", "a2", "a3", "b1", "b2"]
    assert doc.rehacer() and orden(doc) == ["a3", "b1", "b2"]
    doc.invertir()
    assert orden(doc) == ["b2", "b1", "a3"] and not doc.puede_rehacer


def test_duplicar_e_invertir_seleccion(doc):
    assert doc.duplicar([0, 1]) == [2, 3]
    assert orden(doc) == ["a1", "a2", "a1", "a2", "a3", "b1", "b2"]
    doc.invertir([0, 6])
    assert orden(doc)[0] == "b2" and orden(doc)[6] == "a1"


def test_guardar_une_reordena_y_gira(doc, tmp_path):
    doc.mover([3, 4], 0)  # b1 b2 a1 a2 a3
    doc.eliminar([3])  # b1 b2 a1 a3
    doc.rotar([1], 90)
    doc.rotar([3], -90)
    salida = guardar(doc.paginas, tmp_path / "unido.pdf")
    assert textos(salida) == ["b 1", "b 2", "a 1", "a 3"]
    assert giros(salida) == [0, 90, 0, 270]


def test_pagina_duplicada_gira_por_separado(doc, tmp_path):
    doc.eliminar([1, 2, 3, 4])
    doc.duplicar([0])
    doc.rotar([1], 180)
    salida = guardar(doc.paginas, tmp_path / "dup.pdf")
    assert textos(salida) == ["a 1", "a 1"]
    assert giros(salida) == [0, 180]


def test_no_escribe_encima_de_un_origen(doc):
    with pytest.raises(ErrorGuardar):
        guardar(doc.paginas, doc.paginas[0].fuente.ruta)


def test_dividir(doc, tmp_path):
    salidas = dividir(doc.paginas, tmp_path / "partes", "trozo", cada=2)
    assert [s.name for s in salidas] == ["trozo-01.pdf", "trozo-02.pdf", "trozo-03.pdf"]
    assert [textos(s) for s in salidas] == [["a 1", "a 2"], ["a 3", "b 1"], ["b 2"]]


@pytest.mark.parametrize("nombre,modo", [("foto.jpg", "RGB"), ("captura.png", "RGBA"), ("gris.png", "L")])
def test_imagen_a_pdf(tmp_path, nombre, modo):
    origen = tmp_path / nombre
    Image.new(modo, (192, 96), "red" if modo != "L" else 128).save(origen, dpi=(96, 96))
    salida = imagen_a_pdf(origen, tmp_path / "pagina.pdf")
    f = render.abrir(salida)
    assert f.n_paginas == 1 and f.tamanos[0] == pytest.approx((144, 72), abs=0.5)
    im = render.pintar(f, 0, lado_max=96)
    r, g, b = im.getpixel((48, 24))
    assert (r > 200 and g < 60 and b < 60) if modo != "L" else abs(r - 128) < 6
    f.cerrar()


def test_unir_conserva_los_marcadores(pdf_numerado, tmp_path):
    con_indice = tmp_path / "con_indice.pdf"
    with pikepdf.open(str(pdf_numerado("libro.pdf", 4, "libro"))) as pdf:
        with pdf.open_outline() as indice:
            indice.root.append(pikepdf.OutlineItem("Capítulo uno", 0))
            indice.root.append(pikepdf.OutlineItem("Capítulo dos", 2))
        pdf.save(str(con_indice))
    a = render.abrir(pdf_numerado("portada.pdf", 1, "portada"))
    b = render.abrir(con_indice)
    d = Documento()
    d.agregar_fuente(a)
    d.agregar_fuente(b)
    salida = guardar(d.paginas, tmp_path / "todo.pdf")
    a.cerrar()
    b.cerrar()
    assert textos(salida) == ["portada 1", "libro 1", "libro 2", "libro 3", "libro 4"]
    with pikepdf.open(str(salida)) as pdf:
        with pdf.open_outline() as indice:
            titulos = [it.title for it in indice.root]
            destinos = [pdf.pages.index(pikepdf.Page(it.destination[0])) if it.destination is not None else None for it in indice.root]
    assert titulos == ["Capítulo uno", "Capítulo dos"] and destinos == [1, 3]
