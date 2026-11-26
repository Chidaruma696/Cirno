[🇬🇧 English](README.md)

<div align="center">
  <br/>
  <img src="cirno/assets/cirno.png" width="180" alt="Icono de Cirno" />

# Cirno

**チルノ · Suite de PDF para la oficina: une, ordena y edita hojas, saca tablas y datos a Excel, y le hace a un Excel lo que le pidas con tus palabras. Sin IA.**

<br/>

![Windows 10/11](https://img.shields.io/badge/windows-10%2F11%20x64-0078d4?style=for-the-badge&logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/qt-pyside6-41cd52?style=for-the-badge&logo=qt&logoColor=white)
![Licencia Apache 2.0](https://img.shields.io/badge/licencia-Apache%202.0-1b150d?style=for-the-badge)

<br/>

[![Descargar instalador](https://img.shields.io/github/v/release/Chidaruma696/Cirno?label=%E2%AC%87%EF%B8%8F%20DESCARGAR%20INSTALADOR&style=for-the-badge&color=2e7de9)](https://github.com/Chidaruma696/Cirno/releases/latest)

<br/>

*Arrastra los archivos, elige qué quieres y listo · todo en tu equipo · los originales no se tocan*

</div>

---

> [!IMPORTANT]
> **Cirno no envía nada a ningún sitio.** Lee los archivos en tu equipo y escribe los resultados donde le digas; lo único que pregunta a la red es si hay una versión nueva.
> El repositorio ignora `*.pdf` y `*.xlsx` para que los documentos de la oficina nunca acaben en git por accidente.

<br/>

## 📲 Descargar

1. Entra en la [última versión](https://github.com/Chidaruma696/Cirno/releases/latest) y baja `Cirno-x.y.z-setup.exe`.
2. Ejecútalo. Se instala para tu usuario sin pedir permisos de administrador (o para todos los usuarios, si lo eliges). No necesita Python ni nada más.
3. Abre Cirno desde el menú Inicio.

**Las actualizaciones llegan solas.** Al abrirse, Cirno pregunta a GitHub si hay una versión más nueva; si la hay, lo avisa abajo a la derecha. Al pulsar el aviso baja el instalador, lo comprueba contra la huella SHA-256 publicada a su lado, se cierra, instala y vuelve a abrirse. Nunca instala nada sin que lo pidas, y la comprobación se apaga en *Ayuda*.

<br/>

## ❄️ Qué hace

Tres pestañas, una por tarea. Nada usa inteligencia artificial ni internet: todo son reglas que se ejecutan en tu equipo.

| Pestaña | Para qué | Cómo |
| --- | --- | --- |
| **Organizar y editar PDF** | Juntar varios PDF (e imágenes), ordenar las hojas, editarlas, numerarlas, protegerlas, repartirlas en varios archivos | Arrastra los archivos, mueve las hojas con el ratón, doble clic para editar una, y **Guardar PDF** |
| **Extraer datos** | Sacar las tablas y los datos sueltos a Excel, las imágenes o las páginas enteras a PNG o JPG, y el texto a un `.txt` | Arrastra los PDF, revisa lo que Cirno encontró en cada uno y pulsa **Extraer** |
| **Excel en palabras** | Pintar, ordenar, agrupar, quitar repetidos, sumar por grupos… diciéndolo: *«agrupa por Cliente y pinta de rojo los PENDIENTE»* | Elige el libro, escribe la frase, revisa lo que entendió y pulsa **Aplicar** |

### Organizar y editar PDF

Cada hoja es una miniatura en una rejilla. Se seleccionan con el ratón (Ctrl y Mayús para varias) y se arrastran a su sitio; también se pueden soltar más archivos en medio. Hay deshacer y rehacer para todo. Las imágenes entran como una hoja más, sin recomprimir los JPEG. Al unir se conservan los marcadores de cada PDF.

**El editor** (doble clic en una hoja) deja:

- **Escribir** texto en cualquier sitio, con tipo, tamaño, negrita, cursiva y color.
- **Corregir un texto que ya está**: pulsas sobre él, Cirno lo tapa con el color del fondo, toma su tamaño, su color y su tipo de letra, y te lo deja abierto para reescribirlo.
- **Resaltar** (el resaltado se ajusta solo a los renglones), **tapar**, enmarcar, líneas, flechas y **dibujar** a mano una firma.
- Pegar **imágenes** (un sello, una firma escaneada), moverlas, cambiarles el tamaño y copiarlas a todas las hojas.
- **Recortar** la hoja, o todas igual.

**Tapar es borrar.** Lo que queda bajo una tapa no solo se cubre: las letras se eliminan del contenido del PDF, y en un escaneo la zona se pinta dentro de la propia imagen. No se puede buscar, copiar ni destapar. (Queda tapado pero no borrado el texto que el PDF guarda dentro de formularios, que es raro.)

**Herramientas**: numerar las hojas («Página 3 de 12», donde quieras), marca de agua (COPIA, CANCELADO…), intercalar caras y dorsos de un escaneo a dos pasadas, invertir el orden. **Seleccionar**: pares, impares, las apaisadas, las editadas y **las que están en blanco**. **Dividir**: un PDF por hoja, cada tantas, o **un PDF por documento** (corta donde el texto dice «Página 1 de N», para lotes de facturas o recibos). Al guardar se puede poner **contraseña**, **reducir el tamaño** (baja la resolución de escaneos y fotos) y rellenar título y autor.

El archivo original nunca se modifica: Cirno no deja guardar encima de él.

### Extraer datos

Al soltar un PDF, Cirno lo mira y enseña qué hay dentro, y dice qué parece (factura, cotización, pedido, kardex, estado de cuenta…):

- **Tablas**, tengan rayas o no. Las dibujadas se reconstruyen por sus líneas; las demás se intuyen por la alineación del texto. Dos tablas seguidas con encabezados distintos salen separadas; una que sigue durante veinte páginas, como una sola con el encabezado una vez; si va por secciones (un título y el mismo encabezado repetido), el título pasa a ser una columna. Las celdas que doblan línea se juntan con su fila, aunque estén centradas. El renglón de encima da nombre a la hoja.
- **Totales comprobados**: si una tabla trae fila de totales, Cirno suma las filas y dice si cuadra con lo que pone el PDF.
- **Datos sueltos**: lo que no va en tabla (`Cliente: …`, folios, fechas, subtotal, IVA y total, RFC, CURP, CLABE con su dígito de control, folio fiscal, correos, teléfonos) va a una hoja «Datos».
- **Estados de cuenta de proveedor** (`EdoCta-…pdf`, el formato típico de SAP con RESUMEN / Movimientos / Saldo final / CIFRAS CONTROL), con su lector propio: resumen, movimientos, aplicaciones y saldo final, con las sumas cruzadas contra las CIFRAS CONTROL.
- **Imágenes incrustadas**, **páginas enteras como imagen** a la resolución que elijas, y **texto**.

En el Excel cada columna se entiende entera: los importes son números, las fechas son fechas, `168.9 kg` es el número 168.9 con «kg» en el formato (se ve igual y se puede sumar), y si una columna tiene códigos con ceros a la izquierda se queda toda como texto. Un escaneo sin texto se dice que lo es: Cirno no hace OCR.

### Excel en palabras

Escribes lo que quieres, varias cosas a la vez, y Cirno lo convierte en pasos que puedes revisar y desmarcar antes de aplicarlos. Todo va a una copia (`<nombre> - Cirno.xlsx`).

| Dices | Hace |
| --- | --- |
| *«rojo las filas donde Estado sea PENDIENTE; en negrita los Importes mayores de 50 mil»* | Formato condicional de Excel, vivo |
| *«busca los valores iguales de Cliente, agrúpalos»* | Marca los repetidos y junta las filas iguales, con una raya entre grupos |
| *«ordena del más reciente al más antiguo»* | Ordena por la columna de fechas |
| *«quita los repetidos de Folio»*, *«deja solo los PENDIENTE»* | Quita filas |
| *«suma el Importe por Cliente»*, *«cuántos pendientes hay por cliente»* | Una hoja «Resumen» con fórmulas `SUMAR.SI`, `CONTAR.SI.CONJUNTO`… |
| *«pon totales»*, *«añade Importe con IVA»*, *«Importe como moneda»*, *«pon filtros»* | Fila de totales, columna con fórmula, formato de número, filtros y encabezado fijo |

No hay ningún modelo detrás: es un recetario interno con sus palabras clave. Lo que no casa con ninguna receta no se adivina: se dice, y se proponen las que más se parecen. El botón **Ideas** enseña el recetario entero y deja buscar en él («repetidos», «sumar por cliente»…).

<br/>

## ⚙️ Cómo funciona

- **Páginas.** [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (PDFium) pinta las miniaturas; [pikepdf](https://github.com/pikepdf/pikepdf) (qpdf) escribe el PDF final copiando las páginas tal cual. El documento que armas es solo una lista de (archivo, página, giro, marcas, recorte) hasta el momento de guardar.
- **Edición.** Lo que añades se escribe como contenido normal de la página (texto con las fuentes base, rectángulos, imágenes), no como anotaciones: se ve igual en cualquier visor y al imprimir. `cirno/pdf/borrar.py` recorre el contenido siguiendo la posición de cada letra (matrices, fuente, espaciados) y elimina las que caen bajo una tapa.
- **Tablas.** [pdfplumber](https://github.com/jsvine/pdfplumber) da cada palabra con su posición. `cirno/extraccion/tablas.py` agrupa por renglón, parte cada renglón por los huecos anchos, reconoce las filas de encabezado y saca las columnas de los «ríos» en blanco que comparten las filas.
- **Excel.** `cirno/formato/` lleva el intérprete de [Sunny](https://github.com/Chidaruma696/Sunny) para lo de pintar y el recetario (`recetas.py`) para lo demás, todo escrito con [openpyxl](https://openpyxl.readthedocs.io/).

La ventana es Qt ([PySide6](https://doc.qt.io/qtforpython-6/)) con el aspecto del sistema, claro u oscuro según lo tengas. La interfaz está en español.

<br/>

## ⌨️ Línea de comandos

El mismo ejecutable (o `python -m cirno`) acepta argumentos:

```
Cirno.exe informe.pdf                         # abre la ventana con ese PDF en «Extraer datos»
Cirno.exe ventas.xlsx                         # abre la ventana con ese libro en «Formato de Excel»
Cirno.exe --cli C:\pdf\ -o C:\salida          # saca a Excel todos los PDF de la carpeta, sin ventana
Cirno.exe --cli *.pdf --unir -n trimestre.xlsx
Cirno.exe --cli escaneo.pdf --sin-excel --paginas --formato jpg --ppp 300
Cirno.exe --unir-pdf todo.pdf a.pdf b.pdf c.pdf
```

| Opción | Efecto |
| --- | --- |
| `-o CARPETA` | Carpeta de salida (por defecto, junto a cada PDF) |
| `-u`, `--unir` | Un solo Excel con todos los estados de cuenta; cada fila lleva archivo, cuenta y periodo |
| `-n ARCHIVO.xlsx` | Nombre del Excel unido |
| `--imagenes` | Sacar también las imágenes incrustadas |
| `--paginas` | Sacar también cada página como imagen |
| `--texto` | Sacar también el texto a un `.txt` |
| `--sin-excel` | No escribir el Excel |
| `--formato png\|jpg`, `--ppp N` | Formato de las imágenes y resolución de las páginas |
| `--unir-pdf SALIDA.pdf` | Unir los PDF dados, en ese orden, en uno solo |

Editar las hojas y «Excel en palabras» se hacen desde la ventana.
| `--cli` | Trabajar sin abrir la ventana |

<br/>

## 🛠️ Compilar

Necesitas Python 3.11 o superior y, para el instalador, [Inno Setup 6](https://jrsoftware.org/isdl.php).

```powershell
git clone https://github.com/Chidaruma696/Cirno.git
cd Cirno
.\build.ps1                  # .venv + dependencias + PyInstaller + Inno Setup → dist\Cirno-X.Y.Z-setup.exe (+ .sha256)
.\build.ps1 -SinInstalador   # solo dist\Cirno\Cirno.exe
.\build.ps1 -Probar          # las pruebas
```

Para desarrollar sin compilar:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m cirno
.\.venv\Scripts\python -m pytest
```

Estructura:

```
cirno/pdf/render.py          Abrir PDF y pintar páginas (PDFium)
cirno/pdf/documento.py       La lista de hojas: mover, girar, duplicar, quitar, deshacer
cirno/pdf/marcas.py          Lo que se añade a una hoja: texto, cajas, líneas, trazos, imágenes
cirno/pdf/marcas_pdf.py      Escribir las marcas y el recorte dentro del PDF
cirno/pdf/borrar.py          Borrar de verdad el texto y la imagen que quedan bajo una tapa
cirno/pdf/guardar.py         Escribir el PDF: unir, dividir, contraseña, reducir tamaño (pikepdf)
cirno/extraccion/tablas.py   Encontrar tablas, encabezados, secciones, celdas partidas, totales
cirno/extraccion/datos.py    Datos sueltos (etiqueta: valor, RFC, CLABE…) y tipo de documento
cirno/extraccion/valores.py  Entender celdas y columnas: números, fechas, unidades, códigos
cirno/extraccion/analisis.py Qué hay en un PDF
cirno/extraccion/exportar.py Excel con tipos, PNG, JPG, texto
cirno/parser.py              Estados de cuenta de proveedor (columnas por posición, validación)
cirno/excel.py               El libro de un estado de cuenta
cirno/convertir.py           Orquestación por lotes; la usan la ventana y la línea de comandos
cirno/formato/               Excel en palabras: reglas, intérprete, libro y recetario
cirno/updater.py             Actualización desde las releases de GitHub, con SHA-256
cirno/gui/                   Ventana PySide6: organizar, editor, extraer, formato
cirno/cli.py                 Argumentos y punto de entrada
tests/                       pytest
cirno.spec                   PyInstaller (carpeta, sin consola)
installer/Cirno.iss          Inno Setup
build.ps1                    Todo lo anterior en un paso
```

<br/>

## 🗺️ Hoja de ruta

- [ ] OCR para los escaneos.
- [ ] Escribir con cualquier fuente del sistema (hoy: Arial/Helvetica, Times y Courier, alfabeto latino).
- [ ] Rellenar formularios; escalar y poner varias páginas en una hoja.
- [ ] Más formatos de estado de cuenta y factura (cada formato es un módulo de columnas y títulos).
- [ ] Más recetas de Excel (manda las frases que no entienda).

<br/>

## ⚖️ Legal

Cirno es software libre bajo la licencia [Apache 2.0](LICENSE). Los componentes de terceros y sus licencias están en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

La pestaña «Organizar PDF» toma la idea de [PDF Arranger](https://github.com/pdfarranger/pdfarranger); Cirno no contiene código suyo.

Touhou Project y sus personajes pertenecen a Team Shanghai Alice (ZUN); obra de fans no oficial hecha según sus directrices para obras derivadas, sin afiliación ni respaldo.

<br/>

<div align="center">

チルノ

</div>
