"""Fábrica de PDF de prueba: texto colocado en coordenadas (y rayas, si se piden), escrito a
mano con pikepdf para no depender de ningún generador."""

from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest


def _escapar(texto: str) -> bytes:
    crudo = texto.encode("cp1252", errors="replace")
    return crudo.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def escribir_pdf(ruta: Path, paginas: list[dict], tamano=(612, 792)) -> Path:
    """Cada página es {"textos": [(x, y_desde_arriba, texto)], "lineas": [(x0, y0, x1, y1)], "cuerpo": 10}."""
    pdf = pikepdf.Pdf.new()
    fuente = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica,
        Encoding=pikepdf.Name.WinAnsiEncoding))
    ancho, alto = tamano
    for datos in paginas:
        cuerpo = datos.get("cuerpo", 10)
        partes = [b"0.5 w"]
        for x0, y0, x1, y1 in datos.get("lineas", []):
            partes.append(f"{x0} {alto - y0} m {x1} {alto - y1} l S".encode())
        for x, y, texto in datos.get("textos", []):
            partes.append(f"BT /F1 {cuerpo} Tf {x} {alto - y} Td (".encode() + _escapar(texto) + b") Tj ET")
        pagina = pdf.add_blank_page(page_size=tamano)
        pagina.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=fuente))
        pagina.Contents = pdf.make_stream(b"\n".join(partes))
    pdf.save(str(ruta))
    pdf.close()
    return ruta


@pytest.fixture
def hacer_pdf(tmp_path):
    def _hacer(nombre: str, paginas: list[dict], **kw) -> Path:
        return escribir_pdf(tmp_path / nombre, paginas, **kw)
    return _hacer


@pytest.fixture
def pdf_numerado(hacer_pdf):
    """PDF de N páginas cuyo texto es «<prefijo> <n>», para comprobar el orden al guardar."""
    def _hacer(nombre: str, n: int, prefijo: str = "pagina") -> Path:
        return hacer_pdf(nombre, [{"textos": [(72, 100, f"{prefijo} {i}")]} for i in range(1, n + 1)])
    return _hacer
