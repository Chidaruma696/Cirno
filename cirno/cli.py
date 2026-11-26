"""Punto de entrada: sin argumentos abre la ventana; con archivos los precarga; con --cli trabaja sin ventana."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .convertir import expandir


def _enganchar_consola() -> None:
    """Cirno.exe es un programa de ventana (sin consola), así que en modo --cli no tiene salida.
    En Windows se engancha a la consola desde la que lo lanzaron."""
    if sys.platform == "win32" and sys.stdout is None:
        import ctypes

        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
            sys.stderr = sys.stdout
    # Las consolas de Windows suelen ir en cp1252 y no saben pintar ✓ ⚠ ✗ →.
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="cirno",
        description="Suite de PDF: une y ordena páginas, extrae tablas e imágenes, da formato a Excel. "
                    "Sin argumentos abre la ventana.",
    )
    p.add_argument("archivos", nargs="*", help="PDF (o carpetas con PDF); un .xlsx abre la pestaña de formato")
    p.add_argument("-o", "--salida", metavar="CARPETA", help="carpeta de salida (por defecto, junto a cada PDF)")
    p.add_argument("-u", "--unir", action="store_true", help="unir los estados de cuenta en un solo Excel")
    p.add_argument("-n", "--nombre", metavar="ARCHIVO.xlsx", help="nombre del Excel unido")
    p.add_argument("--imagenes", action="store_true", help="sacar también las imágenes incrustadas")
    p.add_argument("--paginas", action="store_true", help="sacar también cada página como imagen")
    p.add_argument("--texto", action="store_true", help="sacar también el texto a un .txt")
    p.add_argument("--sin-excel", action="store_true", help="no escribir el Excel")
    p.add_argument("--formato", choices=("png", "jpg"), default="png", help="formato de las imágenes (png)")
    p.add_argument("--ppp", type=int, default=150, metavar="N", help="resolución de las páginas como imagen (150)")
    p.add_argument("--unir-pdf", metavar="SALIDA.pdf", help="unir los PDF dados, en ese orden, en uno solo")
    p.add_argument("--cli", action="store_true", help="trabajar sin abrir la ventana")
    p.add_argument("-V", "--version", action="version", version=f"{APP_NAME} {__version__}")
    args = p.parse_args(argv)

    pdfs = expandir(args.archivos)
    if args.unir_pdf:
        _enganchar_consola()
        if not pdfs:
            p.error("indica los PDF que quieres unir")
        from .pdf import render
        from .pdf.documento import Documento
        from .pdf.guardar import ErrorGuardar, guardar

        doc = Documento()
        try:
            for pdf in pdfs:
                doc.agregar_fuente(render.abrir(pdf))
            salida = guardar(doc.paginas, args.unir_pdf)
        except (render.ClaveNecesaria, render.PdfIlegible, ErrorGuardar) as e:
            print(f"✗ {e}")
            return 1
        finally:
            for f in doc.fuentes():
                f.cerrar()
        print(f"✓ {salida} ({len(doc)} páginas de {len(pdfs)} PDF)")
        return 0

    if args.cli:
        _enganchar_consola()
        if not pdfs:
            p.error("indica al menos un PDF o una carpeta con PDF")
        from .convertir import convertir

        res = convertir(pdfs, args.salida, args.unir, args.nombre, log=print, imagenes=args.imagenes,
                        paginas=args.paginas, texto=args.texto, formato=args.formato, ppp=args.ppp,
                        con_excel=not args.sin_excel)
        print(f"{len(res.salidas)} archivos, {len(res.avisos)} avisos, {len(res.errores)} errores")
        return 0 if res.ok else 1

    from .gui import ejecutar

    excels = [Path(a) for a in args.archivos if Path(a).suffix.lower() in (".xlsx", ".xlsm") and Path(a).is_file()]
    return ejecutar(pdfs, excel=excels[0] if excels else None)


if __name__ == "__main__":
    sys.exit(main())
