# Avisos de terceros

Cirno se distribuye bajo Apache 2.0 (ver `LICENSE`). Incluye o usa el siguiente software de terceros:

| Componente | Uso | Licencia |
|---|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/) y [Qt](https://www.qt.io/) | Interfaz gráfica | LGPL-3.0. Las bibliotecas de Qt van como DLL separadas dentro de la carpeta de instalación, de modo que pueden sustituirse por otras versiones. |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Extracción de texto con coordenadas del PDF | MIT |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | Motor de PDF que usa pdfplumber | MIT |
| [openpyxl](https://openpyxl.readthedocs.io/) | Escritura de archivos .xlsx | MIT |
| [PyInstaller](https://pyinstaller.org/) | Empaquetado del ejecutable (no forma parte del programa final) | GPL-2.0 con excepción para los ejecutables generados |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Creación del instalador | Inno Setup License |
| [Pillow](https://python-pillow.org/) | Solo para generar el icono (`tools/make_icon.py`) | MIT-CMU |

El diseño de la interfaz sigue la estética de Komi Store (papel y tinta, esquinas rectas, sombras duras).

Touhou Project y sus personajes pertenecen a Team Shanghai Alice (ZUN); obra de fans no oficial hecha según sus directrices para obras derivadas, sin afiliación ni respaldo.
