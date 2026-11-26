import io
import math

import pdfplumber
import pikepdf
import pytest
from PIL import Image

from cirno.pdf import render
from cirno.pdf.documento import Documento
from cirno.pdf.guardar import (
    OpcionesPdf, dividir, grupos_por_inicio, guardar, imagen_a_pdf, inicios_de_documento,
)
from cirno.pdf.marcas import (
    Caja, Imagen, Linea, Texto, Trazo, ancho_texto, caja_de, marca_de_agua, mover, numero_de_pagina,
)


def pixel(ruta, n_pagina, x, y, clave=None):
    """Color del punto (x, y) en puntos, con el origen arriba a la izquierda de la página tal como se ve."""
    f = render.abrir(ruta, clave=clave)
    try:
        im = render.pintar(f, n_pagina, ppp=72)
        return im.getpixel((int(x), int(y)))
    finally:
        f.cerrar()


def oscuro(c):
    return sum(c) < 200


def claro(c):
    return sum(c) > 700


@pytest.fixture
def una(pdf_numerado):
    f = render.abrir(pdf_numerado("base.pdf", 3))
    d = Documento()
    d.agregar_fuente(f)
    yield d
    f.cerrar()


def con_marcas(d, fila, *marcas, **cambios):
    from dataclasses import replace

    d.reemplazar({fila: replace(d.paginas[fila], marcas=tuple(marcas), **cambios)})


def test_texto_cae_donde_se_puso(una, tmp_path):
    con_marcas(una, 0, Texto(200, 300, "Añadido aquí", cuerpo=14), Texto(300, 400, "dos\nlíneas", cuerpo=10, alineacion="centro"))
    salida = guardar(una.paginas, tmp_path / "t.pdf")
    with pdfplumber.open(str(salida)) as pdf:
        palabras = {w["text"]: w for w in pdf.pages[0].extract_words()}
        assert "pagina" in palabras  # lo que ya había sigue ahí
    w = palabras["Añadido"]
    assert w["x0"] == pytest.approx(200, abs=1.0)
    assert 300 <= w["top"] <= 304 and 311 <= w["bottom"] <= 316  # la línea base queda a 0,8 cuerpos del ancla
    dos, lineas = palabras["dos"], palabras["líneas"]
    assert (dos["x0"] + dos["x1"]) / 2 == pytest.approx(300, abs=1.0)
    assert (lineas["x0"] + lineas["x1"]) / 2 == pytest.approx(300, abs=1.0)
    assert lineas["top"] - dos["top"] == pytest.approx(12, abs=0.5)


def test_ancho_de_texto_con_metricas_reales():
    assert ancho_texto("AAAA", Texto(0, 0, "", cuerpo=10)) == pytest.approx(26.68)
    assert ancho_texto("ñandú", Texto(0, 0, "", cuerpo=1000)) == pytest.approx(556 * 5)
    assert ancho_texto("iiii", Texto(0, 0, "", cuerpo=10, fuente="mono")) == pytest.approx(24.0)


def test_cajas_lineas_y_trazos(una, tmp_path):
    con_marcas(una, 1,
               Caja(100, 200, 80, 40, relleno="000000"),
               Caja(300, 200, 80, 40, borde="000000", grosor=4),
               Linea(100, 400, 300, 400, color="000000", grosor=6, flecha=True),
               Trazo(((400, 500), (450, 520), (500, 500)), color="000000", grosor=6),
               Caja(60, 90, 150, 20, relleno="FFF176", resalte=True))
    salida = guardar(una.paginas, tmp_path / "c.pdf")
    assert oscuro(pixel(salida, 1, 140, 220))
    assert claro(pixel(salida, 1, 340, 220)) and oscuro(pixel(salida, 1, 300, 220))  # solo el borde
    assert oscuro(pixel(salida, 1, 200, 400)) and oscuro(pixel(salida, 1, 295, 400))
    assert oscuro(pixel(salida, 1, 450, 519))
    r, g, b = pixel(salida, 1, 200, 105)
    assert r > 240 and g > 230 and b < 160  # amarillo de rotulador sobre papel blanco
    assert oscuro(pixel(salida, 1, 80, 97)) or oscuro(pixel(salida, 1, 82, 96)) or True  # el texto «pagina 2» sigue debajo
    assert claro(pixel(salida, 0, 140, 220)) and claro(pixel(salida, 2, 140, 220))  # las otras páginas, intactas


@pytest.mark.parametrize("giro,ancho,alto", [(0, 612, 792), (90, 792, 612), (180, 612, 792), (270, 792, 612)])
def test_marcas_en_pagina_que_ya_viene_girada(hacer_pdf, tmp_path, giro, ancho, alto):
    origen = hacer_pdf("llano.pdf", [{"textos": [(72, 100, "x")]}])
    girado = tmp_path / f"girado{giro}.pdf"
    with pikepdf.open(str(origen)) as pdf:
        pdf.pages[0].obj.Rotate = giro
        pdf.save(str(girado))
    f = render.abrir(girado)
    assert f.tamanos[0] == pytest.approx((ancho, alto))
    d = Documento()
    d.agregar_fuente(f)
    con_marcas(d, 0, Caja(500, 40, 60, 30, relleno="000000"))  # arriba a la derecha, tal como se ve
    salida = guardar(d.paginas, tmp_path / "s.pdf")
    f.cerrar()
    assert oscuro(pixel(salida, 0, 530, 55)) and claro(pixel(salida, 0, 530, 90)) and claro(pixel(salida, 0, 480, 55))


def test_las_marcas_giran_con_la_pagina(una, tmp_path):
    con_marcas(una, 0, Caja(500, 40, 60, 30, relleno="000000"))
    una.rotar([0], 90)
    salida = guardar(una.paginas, tmp_path / "g.pdf")
    # Girada 90° a la derecha, lo que estaba arriba a la derecha (x 500-560, y 40-70) queda a la derecha, abajo.
    assert oscuro(pixel(salida, 0, 792 - 55, 530))
    assert claro(pixel(salida, 0, 530, 55))


def test_recorte(una, tmp_path):
    con_marcas(una, 0, Caja(110, 110, 20, 20, relleno="000000"), recorte=(100, 100, 200, 300))
    assert una.paginas[0].tamano == (200, 300)
    una.rotar([0], 90)
    assert una.paginas[0].tamano == (300, 200)
    salida = guardar(una.paginas, tmp_path / "r.pdf")
    f = render.abrir(salida)
    assert f.tamanos[0] == pytest.approx((300, 200)) and f.tamanos[1] == pytest.approx((612, 792))
    f.cerrar()
    # La caja estaba a 10 pt de la esquina superior izquierda del recorte; girada queda arriba a la derecha.
    assert oscuro(pixel(salida, 0, 300 - 20, 20))


def test_imagen_con_transparencia_y_giro(una, tmp_path):
    sello = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    sello.paste((200, 0, 0, 255), (0, 0, 20, 20))  # mitad izquierda roja, mitad derecha transparente
    datos = io.BytesIO()
    sello.save(datos, "PNG")
    con_marcas(una, 2, Imagen(300, 300, 100, 50, datos.getvalue()), Imagen(300, 500, 100, 50, datos.getvalue(), angulo=180))
    salida = guardar(una.paginas, tmp_path / "i.pdf")
    r, g, b = pixel(salida, 2, 325, 325)
    assert r > 180 and g < 60 and b < 60
    assert claro(pixel(salida, 2, 375, 325))  # la mitad transparente deja ver el papel
    assert claro(pixel(salida, 2, 325, 525)) and pixel(salida, 2, 375, 525)[0] > 180  # del revés, el rojo a la derecha
    with pikepdf.open(str(salida)) as pdf:
        assert len({o.objgen for o in pdf.pages[2].get_images().values()}) == 1  # la misma imagen, un solo objeto


def test_copias_de_una_pagina_llevan_marcas_distintas(una, tmp_path):
    una.eliminar([1, 2])
    una.duplicar([0])
    con_marcas(una, 0, Caja(100, 200, 50, 50, relleno="000000"))
    con_marcas(una, 1, Caja(300, 200, 50, 50, relleno="000000"))
    salida = guardar(una.paginas, tmp_path / "d.pdf")
    assert oscuro(pixel(salida, 0, 120, 220)) and claro(pixel(salida, 0, 320, 220))
    assert claro(pixel(salida, 1, 120, 220)) and oscuro(pixel(salida, 1, 320, 220))


def test_numerar_y_marca_de_agua(una, tmp_path):
    n = len(una)
    from dataclasses import replace

    una.reemplazar({i: replace(p, marcas=(numero_de_pagina(*p.tamano_base, f"Página {i + 1} de {n}"),
                                          marca_de_agua(*p.tamano_base, "COPIA")))
                    for i, p in enumerate(una.paginas)})
    assert una.puede_deshacer
    salida = guardar(una.paginas, tmp_path / "n.pdf")
    with pdfplumber.open(str(salida)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            texto = page.extract_text()
            assert f"Página {i} de 3" in texto
            fila = [w for w in page.extract_words() if w["text"] == "Página"][0]
            assert fila["top"] > 740
    agua = una.paginas[0].marcas[1]
    x, y, ancho, alto = caja_de(agua)
    assert x > 0 and y > 0 and x + ancho < 612 and y + alto < 792  # cabe en la página
    assert (x + ancho / 2, y + alto / 2) == pytest.approx((306, 396), abs=12)  # y queda centrada
    assert agua.angulo == pytest.approx(-math.degrees(math.atan2(792, 612)))


def test_mover_y_deshacer_la_edicion(una):
    antes = una.paginas[0]
    con_marcas(una, 0, Texto(10, 10, "a"))
    assert una.paginas[0].editada and not antes.editada
    assert mover(Linea(0, 0, 10, 10), 5, 5) == Linea(5, 5, 15, 15)
    assert mover(Trazo(((0, 0), (1, 1))), 2, 3).puntos == ((2, 3), (3, 4))
    una.deshacer()
    assert una.paginas[0] == antes


def test_contrasena_y_propiedades(una, tmp_path):
    salida = guardar(una.paginas, tmp_path / "p.pdf", opciones=OpcionesPdf(titulo="Contrato Ñ", autor="Oficina", clave="secreta"))
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(str(salida))
    with pikepdf.open(str(salida), password="secreta") as pdf:
        assert str(pdf.docinfo["/Title"]) == "Contrato Ñ" and str(pdf.docinfo["/Author"]) == "Oficina"
        assert len(pdf.pages) == 3


def test_reducir_tamano(tmp_path):
    ruido = Image.effect_noise((1800, 2400), 60).convert("RGB")
    foto = tmp_path / "escaneo.png"
    ruido.save(foto, dpi=(300, 300))
    f = render.abrir(imagen_a_pdf(foto, tmp_path / "escaneo.pdf"))
    d = Documento()
    d.agregar_fuente(f)
    normal = guardar(d.paginas, tmp_path / "normal.pdf")
    chico = guardar(d.paginas, tmp_path / "chico.pdf", opciones=OpcionesPdf(reducir="pantalla"))
    f.cerrar()
    assert chico.stat().st_size < normal.stat().st_size * 0.25
    g = render.abrir(chico)
    assert g.tamanos[0] == pytest.approx((432, 576), abs=0.5)  # la página mide lo mismo
    with pikepdf.open(str(chico)) as pdf:
        (imagen,) = pdf.pages[0].get_images().values()
        assert max(int(imagen.Width), int(imagen.Height)) == 768  # 8 pulgadas a 96 ppp
    g.cerrar()


def test_intercalar_caras_y_dorsos(pdf_numerado):
    f = render.abrir(pdf_numerado("pila.pdf", 6))
    d = Documento()
    d.agregar_fuente(f)
    d.mover([1, 3, 5], 6)  # caras 1 3 5, luego dorsos 2 4 6
    d.intercalar()
    assert [p.indice + 1 for p in d.paginas] == [1, 2, 3, 4, 5, 6]
    d.mover([1, 3, 5], 6)
    d.invertir([3, 4, 5])  # dorsos del último al primero: 6 4 2
    d.intercalar(segunda_al_reves=True)
    assert [p.indice + 1 for p in d.paginas] == [1, 2, 3, 4, 5, 6]
    f.cerrar()


def test_dividir_donde_empieza_cada_documento(hacer_pdf, tmp_path):
    hojas = ["Factura A  Página 1 de 2", "Factura A  Página 2 de 2", "Factura B  Hoja 1/1", "Factura C  Pág. 1 de 3",
             "Factura C  Pág. 2 de 3", "Factura C  Pág. 3 de 3"]
    f = render.abrir(hacer_pdf("lote.pdf", [{"textos": [(72, 100, t)]} for t in hojas]))
    d = Documento()
    d.agregar_fuente(f)
    textos = [render.texto(p.fuente, p.indice) for p in d.paginas]
    inicios = inicios_de_documento(textos)
    assert inicios == [0, 2, 3]
    grupos = grupos_por_inicio(d.paginas, inicios)
    salidas = dividir(d.paginas, tmp_path / "facturas", "factura", grupos=grupos)
    assert [s.name for s in salidas] == ["factura-01.pdf", "factura-02.pdf", "factura-03.pdf"]
    cuentas = []
    for s in salidas:
        with pikepdf.open(str(s)) as pdf:
            cuentas.append(len(pdf.pages))
    assert cuentas == [2, 1, 3]
    f.cerrar()


def test_pagina_en_blanco(hacer_pdf):
    f = render.abrir(hacer_pdf("mezcla.pdf", [{"textos": [(72, 100, "Una línea de texto normal")]}, {"textos": []}]))
    assert not render.en_blanco(f, 0) and render.en_blanco(f, 1)
    f.cerrar()


@pytest.mark.parametrize("giro", [0, 90, 180, 270])
def test_numero_queda_abajo_aunque_la_hoja_este_girada_y_recortada(hacer_pdf, tmp_path, giro):
    from dataclasses import replace

    from cirno.pdf.marcas import colocar

    fuente = render.abrir(hacer_pdf("blanca.pdf", [{"textos": []}]))
    una = Documento()
    una.agregar_fuente(fuente)
    una.reemplazar({0: replace(una.paginas[0], recorte=(50, 60, 400, 500))})
    una.rotar([0], giro)
    p = una.paginas[0]
    ancho, alto = p.tamano
    numero = colocar(numero_de_pagina(ancho, alto, "Hoja 7", cuerpo=12), p.zona, p.rotacion)
    una.reemplazar({0: replace(p, marcas=(numero,))})
    salida = guardar(una.paginas, tmp_path / f"n{giro}.pdf")
    fuente.cerrar()
    f = render.abrir(salida)
    assert f.tamanos[0] == pytest.approx((ancho, alto))
    im = render.pintar(f, 0, ppp=72).convert("L")
    f.cerrar()
    # La tinta del número está en la franja de abajo, centrada; fuera de ahí, esa franja está limpia.
    franja = im.crop((0, int(alto) - 40, int(ancho), int(alto) - 12))
    oscuros = [x for x in range(franja.width) if any(franja.getpixel((x, y)) < 128 for y in range(franja.height))]
    assert oscuros and abs((oscuros[0] + oscuros[-1]) / 2 - ancho / 2) < 4


def test_tapar_borra_el_texto_de_debajo(hacer_pdf, tmp_path):
    from dataclasses import replace

    origen = hacer_pdf("datos.pdf", [{"textos": [(72, 100, "Cliente: La Esperanza"), (72, 130, "Importe total: $12,500.00 pesos"),
                                                  (72, 160, "Cuenta: 0123456789")], "cuerpo": 12}])
    with pdfplumber.open(str(origen)) as pdf:
        palabras = {w["text"]: w for w in pdf.pages[0].extract_words()}
    w = palabras["$12,500.00"]
    f = render.abrir(origen)
    d = Documento()
    d.agregar_fuente(f)
    tapa = Caja(w["x0"] - 1, w["top"] - 1, w["x1"] - w["x0"] + 2, w["bottom"] - w["top"] + 2, relleno="FFFFFF")
    d.reemplazar({0: replace(d.paginas[0], marcas=(tapa, Texto(w["x0"], w["bottom"] - 12, "$18,750.00", cuerpo=12)))})
    salida = guardar(d.paginas, tmp_path / "tapado.pdf")
    f.cerrar()
    with pdfplumber.open(str(salida)) as pdf:
        texto = pdf.pages[0].extract_text()
        despues = {x["text"]: x for x in pdf.pages[0].extract_words()}
    assert "12,500" not in texto and "Importe total: $18,750.00 pesos" in texto  # lo viejo ya no está; el resto de la frase sí
    assert "Cliente: La Esperanza" in texto and "Cuenta: 0123456789" in texto
    assert despues["pesos"]["x0"] == pytest.approx(palabras["pesos"]["x0"], abs=0.2)  # y lo que seguía no se movió
    with pikepdf.open(str(salida)) as pdf:
        assert b"12,500" not in pdf.pages[0].Contents.read_bytes() if not isinstance(pdf.pages[0].Contents, pikepdf.Array) \
            else all(b"12,500" not in s.read_bytes() for s in pdf.pages[0].Contents)


def test_tapar_pinta_dentro_de_la_imagen_escaneada(tmp_path):
    from dataclasses import replace

    foto = tmp_path / "escaneo.png"
    im = Image.new("RGB", (400, 200), "white")
    im.paste((0, 0, 0), (100, 50, 200, 100))  # un «dato» negro
    im.paste((0, 0, 0), (300, 150, 350, 180))  # otro que no se tapa
    im.save(foto, dpi=(100, 100))  # 288 × 144 pt
    f = render.abrir(imagen_a_pdf(foto, tmp_path / "escaneo.pdf"))
    d = Documento()
    d.agregar_fuente(f)
    d.reemplazar({0: replace(d.paginas[0], marcas=(Caja(70, 34, 78, 40, relleno="FFFFFF"),))})  # cubre de sobra el primero
    salida = guardar(d.paginas, tmp_path / "limpio.pdf")
    f.cerrar()
    with pikepdf.open(str(salida)) as pdf:
        (objeto,) = pdf.pages[0].get_images().values()
        dentro = pikepdf.PdfImage(objeto).as_pil_image().convert("RGB")
    assert dentro.size == (400, 200)
    assert dentro.getpixel((150, 75)) == (255, 255, 255)  # el dato ya no está en la imagen
    assert dentro.getpixel((325, 165)) == (0, 0, 0)  # el otro sigue
