"""Punto de entrada: sin argumentos abre la ventana; con PDF los precarga; con --cli convierte sin ventana."""

from __future__ import annotations

import argparse
import sys

from . import APP_NAME, __version__
from .convertir import expandir


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="cirno",
        description="Convierte estados de cuenta en PDF a Excel. Sin argumentos abre la ventana.",
    )
    p.add_argument("pdf", nargs="*", help="PDF a convertir, o carpetas con PDF")
    p.add_argument("-o", "--salida", metavar="CARPETA", help="carpeta de salida (por defecto, junto a cada PDF)")
    p.add_argument("-u", "--unir", action="store_true", help="unir todo en un solo Excel")
    p.add_argument("-n", "--nombre", metavar="ARCHIVO.xlsx", help="nombre del Excel unido")
    p.add_argument("--cli", action="store_true", help="convertir sin abrir la ventana")
    p.add_argument("-V", "--version", action="version", version=f"{APP_NAME} {__version__}")
    args = p.parse_args(argv)

    pdfs = expandir(args.pdf)
    if args.cli:
        if not pdfs:
            p.error("indica al menos un PDF o una carpeta con PDF")
        from .convertir import convertir

        # Las consolas de Windows suelen ir en cp1252 y no saben pintar ✓ ⚠ ✗ →.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        res = convertir(pdfs, args.salida, args.unir, args.nombre, log=print)
        print(f"{len(res.salidas)} Excel, {len(res.avisos)} avisos, {len(res.errores)} errores")
        return 0 if res.ok else 1

    from .gui import ejecutar

    return ejecutar(pdfs, args.salida, args.unir)


if __name__ == "__main__":
    sys.exit(main())
