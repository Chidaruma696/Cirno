[🇬🇧 English](README.en.md)

<div align="center">
  <br/>
  <img src="cirno/assets/cirno.png" width="180" alt="Icono de Cirno" />

# Cirno

**チルノ · Estados de cuenta en PDF convertidos a Excel, con estética Komi.**

<br/>

![Windows 10/11](https://img.shields.io/badge/windows-10%2F11%20x64-0078d4?style=for-the-badge&logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/qt-pyside6-41cd52?style=for-the-badge&logo=qt&logoColor=white)
![Licencia Apache 2.0](https://img.shields.io/badge/licencia-Apache%202.0-1b150d?style=for-the-badge)

<br/>

[![Descargar instalador](https://img.shields.io/github/v/release/Chidaruma696/Cirno?label=%E2%AC%87%EF%B8%8F%20DESCARGAR%20INSTALADOR&style=for-the-badge&color=2e7de9)](https://github.com/Chidaruma696/Cirno/releases/latest)

<br/>

*Arrastra los PDF, pulsa Convertir y listo · todo en tu equipo · sin subir nada a ningún sitio*

</div>

---

> [!IMPORTANT]
> **Cirno no envía nada a ningún sitio.** Lee los PDF en tu equipo y escribe los Excel donde le digas.
> Los estados de cuenta contienen datos personales: el repositorio ignora `*.pdf` y `*.xlsx` para que nunca acaben en git por accidente.

<br/>

## 📲 Descargar

1. Entra en la [última versión](https://github.com/Chidaruma696/Cirno/releases/latest) y baja `Cirno-x.y.z-setup.exe`.
2. Ejecútalo. Se instala para tu usuario sin pedir permisos de administrador (o para todos los usuarios, si lo eliges). No necesita Python ni nada más.
3. Abre Cirno desde el menú Inicio. Las versiones siguientes se instalan encima.

<br/>

## ❄️ Qué hace

| Entrada | Salida | Cómo |
| --- | --- | --- |
| Estados de cuenta en PDF del formato **Bachoco** (`EdoCta-…pdf`), uno o muchos | Un `.xlsx` por PDF, o un solo libro con todo | Arrastra los PDF a la ventana y pulsa **CONVERTIR** |

Cada libro trae cuatro hojas, con fechas y montos como valores reales (no texto), filtros y encabezado fijo:

- **Resumen**: cuenta, razón social, sociedad, periodo, fecha de emisión y el bloque RESUMEN (saldo inicial, compras, cargos, pagos, bonificaciones, cancelaciones, saldo final).
- **Movimientos**: fecha, tipo (saldo inicial / cargo / abono / aplicación), referencia, asignación, cargos, abonos, saldo final y el detalle de aplicación de cada pago, igual que en el PDF.
- **Aplicaciones**: el detalle de aplicación en formato plano (fecha y referencia del pago, importe aplicado, nota de crédito, documento aplicado), listo para tablas dinámicas.
- **Saldo final**: los documentos pendientes con vencimiento, cargo, abono, saldo y descripción.

Las filas **CIFRAS CONTROL** del PDF se copian como totales y, además, Cirno suma por su cuenta cargos, abonos y pagos aplicados y avisa si algo no cuadra (hoja **Avisos**). Los montos con guion final (`25,000.42-`) se convierten en negativos.

Si le das un PDF que no es de este formato, no se queda callado: vuelca las tablas que encuentre (o el texto línea a línea) en un Excel y lo marca como aviso.

<br/>

## ⚙️ Cómo funciona

El PDF no contiene tablas de verdad, solo texto colocado en coordenadas. Cirno lee cada palabra con su posición ([pdfplumber](https://github.com/jsvine/pdfplumber)), agrupa por renglón, reparte cada palabra en su columna según la posición horizontal (calibrada con varios estados de cuenta) y reconoce las secciones por sus títulos: `RESUMEN`, `Movimientos del periodo`, `Detalles de Saldo Final`, `CIFRAS CONTROL`. No depende de la fila de encabezados, porque en algunos PDF el extractor no la devuelve. Un renglón con fecha es un movimiento; un renglón sin fecha pero con importe en «Pago» es la aplicación del movimiento anterior. Las tablas que saltan de página se siguen sin problema.

El Excel lo escribe [openpyxl](https://openpyxl.readthedocs.io/). La ventana es Qt ([PySide6](https://doc.qt.io/qtforpython-6/)) con la estética Komi: papel y tinta, esquinas rectas, sombras duras, paleta hielo.

<br/>

## ⌨️ Línea de comandos

El mismo ejecutable (o `python -m cirno`) acepta argumentos:

```
Cirno.exe EdoCta-1.pdf EdoCta-2.pdf          # abre la ventana con esos PDF ya cargados
Cirno.exe --cli C:\estados\ -o C:\salida     # convierte todos los PDF de la carpeta, sin ventana
Cirno.exe --cli *.pdf --unir -n trimestre.xlsx
```

| Opción | Efecto |
| --- | --- |
| `-o CARPETA` | Carpeta de salida (por defecto, junto a cada PDF) |
| `-u`, `--unir` | Un solo Excel con todos los estados; cada fila lleva archivo, cuenta y periodo |
| `-n ARCHIVO.xlsx` | Nombre del Excel unido |
| `--cli` | Convertir sin abrir la ventana |

<br/>

## 🛠️ Compilar

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

<br/>

## 🗺️ Hoja de ruta

- [ ] Más formatos de estado de cuenta y factura (cada formato es un módulo de columnas y títulos).
- [ ] Exportar también a CSV.
- [ ] Tema oscuro.

<br/>

## ⚖️ Legal

Cirno es software libre bajo la licencia [Apache 2.0](LICENSE). Los componentes de terceros y sus licencias están en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Bachoco es una marca de Industrias Bachoco, S.A.B. de C.V.; Cirno no tiene relación con la empresa, solo lee el formato de sus estados de cuenta.

Touhou Project y sus personajes pertenecen a Team Shanghai Alice (ZUN); obra de fans no oficial hecha según sus directrices para obras derivadas, sin afiliación ni respaldo.

<br/>

<div align="center">

チルノ

</div>
