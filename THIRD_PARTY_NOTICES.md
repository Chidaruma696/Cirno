# Avisos de terceros

Cirno se distribuye bajo Apache 2.0 (ver `LICENSE`). Incluye o usa el siguiente software de terceros:

| Componente | Uso | Licencia |
|---|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/) y [Qt](https://www.qt.io/) | Interfaz gráfica | LGPL-3.0. Las bibliotecas de Qt van como DLL separadas dentro de la carpeta de instalación, de modo que pueden sustituirse por otras versiones. |
| [pikepdf](https://github.com/pikepdf/pikepdf) | Escribir los PDF: unir, reordenar, girar, dividir; sacar las imágenes incrustadas | MPL-2.0 |
| [qpdf](https://github.com/qpdf/qpdf) | Motor de PDF que usa pikepdf | Apache-2.0 |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | Pintar las páginas (miniaturas, páginas como imagen) | Apache-2.0 o BSD-3-Clause |
| [PDFium](https://pdfium.googlesource.com/pdfium/) | Motor de pintado que usa pypdfium2 | BSD-3-Clause y Apache-2.0, con componentes de terceros bajo sus propias licencias |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Texto con coordenadas y tablas dibujadas del PDF | MIT |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | Motor de texto que usa pdfplumber | MIT |
| [openpyxl](https://openpyxl.readthedocs.io/) | Leer y escribir archivos .xlsx | MIT |
| [Pillow](https://python-pillow.org/) | Leer y escribir PNG y JPG; generar el icono (`tools/make_icon.py`) | MIT-CMU |
| [lxml](https://lxml.de/) | Dependencia de pikepdf (metadatos) | BSD-3-Clause |
| [PyInstaller](https://pyinstaller.org/) | Empaquetado del ejecutable (no forma parte del programa final) | GPL-2.0 con excepción para los ejecutables generados |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Creación del instalador | Inno Setup License |

La pestaña «Organizar PDF» toma la idea de [PDF Arranger](https://github.com/pdfarranger/pdfarranger) (GPL-3.0): una rejilla de hojas que se ordenan arrastrándolas. Cirno no contiene código de PDF Arranger; está escrito desde cero sobre pikepdf.

El formato condicional dicho en palabras es el motor de [Sunny](https://github.com/Chidaruma696/Sunny) (Apache 2.0, del mismo autor), integrado en `cirno/formato/`.

Touhou Project y sus personajes pertenecen a Team Shanghai Alice (ZUN); obra de fans no oficial hecha según sus directrices para obras derivadas, sin afiliación ni respaldo.
