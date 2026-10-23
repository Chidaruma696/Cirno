[English](README.en.md) · **Español**

<p align="center">
  <img src="cirno/assets/cirno.png" width="128" alt="Cirno">
</p>

<h1 align="center">Cirno <sub>チルノ</sub></h1>

<p align="center">
  <b>Estados de cuenta en PDF → Excel.</b> Arrastra, convierte, listo.
</p>

<p align="center">
  <img alt="Windows" src="https://img.shields.io/badge/Windows%2010%2F11-x64-2E7DE9?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-10233A?style=flat-square">
  <img alt="Qt" src="https://img.shields.io/badge/Qt-PySide6-10233A?style=flat-square">
  <img alt="Licencia" src="https://img.shields.io/badge/licencia-Apache%202.0-10233A?style=flat-square">
</p>

<p align="center">
  <a href="https://github.com/Chidaruma696/Cirno/releases/latest">
    <img alt="Descargar instalador" src="https://img.shields.io/badge/⬇️%20DESCARGAR%20INSTALADOR-Cirno--setup.exe-2E7DE9?style=for-the-badge">
  </a>
</p>

---

## Descargar

Baja `Cirno-X.Y.Z-setup.exe` de la [última release](https://github.com/Chidaruma696/Cirno/releases/latest) y ejecútalo. Se instala para tu usuario sin pedir permisos de administrador (o para todos los usuarios, si lo eliges). No necesita Python ni nada más instalado.

## Qué es

| Entrada | Salida | Cómo |
|---|---|---|
| Estados de cuenta en PDF del formato **Bachoco** (`EdoCta-…pdf`), uno o muchos | Un `.xlsx` por PDF, o un solo libro con todo | Arrastra los PDF a la ventana y pulsa **CONVERTIR** |

Cada libro trae cuatro hojas, con fechas y montos como valores reales (no texto), filtros y encabezado fijo:

- **Resumen**: cuenta, razón social, sociedad, periodo, fecha de emisión y el bloque RESUMEN (saldo inicial, compras, cargos, pagos, bonificaciones, cancelaciones, saldo final).
- **Movimientos**: fecha, tipo (saldo inicial / cargo / abono / aplicación), referencia, asignación, cargos, abonos, saldo final y el detalle de aplicación de cada pago, igual que en el PDF.
- **Aplicaciones**: el detalle de aplicación en formato plano (fecha y referencia del pago, importe aplicado, nota de crédito, documento aplicado), listo para tablas dinámicas.
- **Saldo final**: los documentos pendientes con vencimiento, cargo, abono, saldo y descripción.

Las filas **CIFRAS CONTROL** del PDF se copian como totales y, además, Cirno suma por su cuenta cargos, abonos y pagos aplicados y avisa si algo no cuadra (hoja **Avisos**). Los montos con guion final (`25,000.42-`) se convierten en negativos.

Si le das un PDF que no es de este formato, no se queda callado: vuelca las tablas que encuentre (o el texto línea a línea) en un Excel y lo marca como aviso.

## Cómo funciona

El PDF no contiene tablas de verdad, solo texto colocado en coordenadas. Cirno lee cada palabra con su posición ([pdfplumber](https://github.com/jsvine/pdfplumber)), agrupa por renglón, reparte cada palabra en su columna según la posición horizontal (calibrada con varios estados de cuenta) y reconoce las secciones por sus títulos: `RESUMEN`, `Movimientos del periodo`, `Detalles de Saldo Final`, `CIFRAS CONTROL`. No depende de la fila de encabezados, porque en algunos PDF el extractor no la devuelve. Un renglón con fecha es un movimiento; un renglón sin fecha pero con importe en «Pago» es la aplicación del movimiento anterior. Las tablas que saltan de página se siguen sin problema.

El Excel lo escribe [openpyxl](https://openpyxl.readthedocs.io/). La ventana es Qt ([PySide6](https://doc.qt.io/qtforpython-6/)) con la estética Komi: papel y tinta, esquinas rectas, sombras duras, paleta hielo.

### Línea de comandos

El mismo ejecutable (o `python -m cirno`) acepta argumentos:

```
Cirno.exe EdoCta-1.pdf EdoCta-2.pdf          # abre la ventana con esos PDF ya cargados
Cirno.exe --cli C:\estados\ -o C:\salida     # convierte todos los PDF de la carpeta, sin ventana
Cirno.exe --cli *.pdf --unir -n trimestre.xlsx
```

| Opción | Efecto |
|---|---|
| `-o CARPETA` | Carpeta de salida (por defecto, junto a cada PDF) |
| `-u`, `--unir` | Un solo Excel con todos los estados; cada fila lleva archivo, cuenta y periodo |
| `-n ARCHIVO.xlsx` | Nombre del Excel unido |
| `--cli` | Convertir sin abrir la ventana |

## Compilar

Necesitas Python 3.11 o superior y, para el instalador, [Inno Setup 6](https://jrsoftware.org/isdl.php).

```powershell
git clone https://github.com/Chidaruma696/Cirno.git
cd Cirno
.\build.ps1                  # .venv + dependencias + PyInstaller + Inno Setup → dist\Cirno-X.Y.Z-setup.exe
.\build.ps1 -SinInstalador   # solo dist\Cirno\Cirno.exe
```

Para desarrollar sin compilar:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m cirno
```

Estructura:

```
cirno/parser.py     PDF → EstadoCuenta (columnas por posición, secciones por título, validación)
cirno/excel.py      EstadoCuenta → .xlsx (hojas, formatos, totales)
cirno/convertir.py  Orquestación: lotes, unir, respaldo genérico
cirno/gui.py        Ventana PySide6 (arrastrar y soltar, hilo de trabajo, registro)
cirno/theme.py      QSS Komi, paleta Cirno
cirno/cli.py        Argumentos y punto de entrada
cirno.spec          PyInstaller (carpeta, sin consola)
installer/Cirno.iss Inno Setup
build.ps1           Todo lo anterior en un paso
```

## Hoja de ruta

- [ ] Más formatos de estado de cuenta / factura (cada formato es un módulo de columnas y títulos).
- [ ] Exportar también a CSV.
- [ ] Tema oscuro.

## Legal

Cirno es software libre bajo la licencia [Apache 2.0](LICENSE). Los componentes de terceros y sus licencias están en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Cirno procesa los PDF **en tu equipo**: no sube nada a ningún sitio. Los estados de cuenta contienen datos personales; el repositorio ignora `*.pdf` y `*.xlsx` para que no acaben en git por accidente.

Bachoco es una marca de Industrias Bachoco, S.A.B. de C.V.; Cirno no tiene relación con la empresa, solo lee el formato de sus estados de cuenta.

Touhou Project y sus personajes pertenecen a Team Shanghai Alice (ZUN); obra de fans no oficial hecha según sus directrices para obras derivadas, sin afiliación ni respaldo.

<p align="center"><b>チルノ</b></p>
