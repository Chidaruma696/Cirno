**English** · [Español](README.md)

<p align="center">
  <img src="cirno/assets/cirno.png" width="128" alt="Cirno">
</p>

<h1 align="center">Cirno <sub>チルノ</sub></h1>

<p align="center">
  <b>PDF account statements → Excel.</b> Drag, convert, done.
</p>

<p align="center">
  <img alt="Windows" src="https://img.shields.io/badge/Windows%2010%2F11-x64-2E7DE9?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-10233A?style=flat-square">
  <img alt="Qt" src="https://img.shields.io/badge/Qt-PySide6-10233A?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-10233A?style=flat-square">
</p>

<p align="center">
  <a href="https://github.com/Chidaruma696/Cirno/releases/latest">
    <img alt="Download installer" src="https://img.shields.io/badge/⬇️%20DOWNLOAD%20INSTALLER-Cirno--setup.exe-2E7DE9?style=for-the-badge">
  </a>
</p>

---

## Download

Grab `Cirno-X.Y.Z-setup.exe` from the [latest release](https://github.com/Chidaruma696/Cirno/releases/latest) and run it. It installs per user without asking for administrator rights (or for all users, if you choose so). No Python or anything else required.

## What it is

| Input | Output | How |
|---|---|---|
| PDF account statements in the **Bachoco** format (`EdoCta-…pdf`), one or many | One `.xlsx` per PDF, or a single workbook with everything | Drag the PDFs onto the window and press **CONVERTIR** |

Every workbook has four sheets, with dates and amounts as real values (not text), filters and a frozen header:

- **Resumen**: account, customer, company, period, issue date and the RESUMEN block (opening balance, purchases, charges, payments, allowances, cancellations, closing balance).
- **Movimientos**: date, type (opening balance / charge / credit / application), reference, assignment, charges, credits, running balance and the application detail of each payment, just like the PDF.
- **Aplicaciones**: the application detail as a flat table (payment date and reference, applied amount, credit note, applied document), ready for pivot tables.
- **Saldo final**: outstanding documents with due date, charge, credit, balance and description.

The PDF's **CIFRAS CONTROL** rows are copied as totals and, on top of that, Cirno adds up charges, credits and applied payments on its own and warns if anything does not match (**Avisos** sheet). Amounts with a trailing dash (`25,000.42-`) become negative numbers.

Given a PDF in some other format, it does not stay silent: it dumps whatever tables it finds (or the text line by line) into an Excel file and flags it as a warning.

## How it works

The PDF has no real tables, only text placed at coordinates. Cirno reads every word with its position ([pdfplumber](https://github.com/jsvine/pdfplumber)), groups words into rows, assigns each word to a column by its horizontal position (calibrated with several statements) and detects sections by their titles: `RESUMEN`, `Movimientos del periodo`, `Detalles de Saldo Final`, `CIFRAS CONTROL`. It does not rely on the header row, since some PDFs do not return it to the extractor. A row with a date is a movement; a row without a date but with an amount under "Pago" is an application of the previous movement. Tables spanning pages are followed seamlessly.

Excel files are written by [openpyxl](https://openpyxl.readthedocs.io/). The window is Qt ([PySide6](https://doc.qt.io/qtforpython-6/)) with the Komi look: paper and ink, square corners, hard shadows, ice palette. The UI is in Spanish.

### Command line

The same executable (or `python -m cirno`) takes arguments:

```
Cirno.exe EdoCta-1.pdf EdoCta-2.pdf          # opens the window with those PDFs preloaded
Cirno.exe --cli C:\statements\ -o C:\out     # converts every PDF in the folder, no window
Cirno.exe --cli *.pdf --unir -n quarter.xlsx
```

| Option | Effect |
|---|---|
| `-o FOLDER` | Output folder (default: next to each PDF) |
| `-u`, `--unir` | One workbook with every statement; each row carries file, account and period |
| `-n FILE.xlsx` | Name of the merged workbook |
| `--cli` | Convert without opening the window |

## Build

You need Python 3.11+ and, for the installer, [Inno Setup 6](https://jrsoftware.org/isdl.php).

```powershell
git clone https://github.com/Chidaruma696/Cirno.git
cd Cirno
.\build.ps1                  # .venv + deps + PyInstaller + Inno Setup → dist\Cirno-X.Y.Z-setup.exe
.\build.ps1 -SinInstalador   # only dist\Cirno\Cirno.exe
```

To develop without building:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m cirno
```

Layout:

```
cirno/parser.py     PDF → EstadoCuenta (columns by position, sections by title, validation)
cirno/excel.py      EstadoCuenta → .xlsx (sheets, formats, totals)
cirno/convertir.py  Orchestration: batches, merge, generic fallback
cirno/gui.py        PySide6 window (drag and drop, worker thread, log)
cirno/theme.py      Komi QSS, Cirno palette
cirno/cli.py        Arguments and entry point
cirno.spec          PyInstaller (one folder, no console)
installer/Cirno.iss Inno Setup
build.ps1           All of the above in one step
```

## Roadmap

- [ ] More statement / invoice formats (each format is a module of columns and titles).
- [ ] CSV export.
- [ ] Dark theme.

## Legal

Cirno is free software under the [Apache 2.0](LICENSE) license. Third-party components and their licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Cirno processes PDFs **on your machine**: nothing is uploaded anywhere. Statements contain personal data; the repository ignores `*.pdf` and `*.xlsx` so they never end up in git by accident.

Bachoco is a trademark of Industrias Bachoco, S.A.B. de C.V.; Cirno is not related to the company, it only reads the format of its statements.

Touhou Project and its characters belong to Team Shanghai Alice (ZUN); unofficial fan work made under their guidelines for derivative works, with no affiliation or endorsement.

<p align="center"><b>チルノ</b></p>
