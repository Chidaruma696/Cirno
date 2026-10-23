[🇪🇸 Español](README.es.md)

<div align="center">
  <br/>
  <img src="cirno/assets/cirno.png" width="180" alt="Cirno icon" />

# Cirno

**チルノ · PDF account statements turned into Excel, with the Komi look.**

<br/>

![Windows 10/11](https://img.shields.io/badge/windows-10%2F11%20x64-0078d4?style=for-the-badge&logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/qt-pyside6-41cd52?style=for-the-badge&logo=qt&logoColor=white)
![Apache 2.0 license](https://img.shields.io/badge/license-Apache%202.0-1b150d?style=for-the-badge)

<br/>

[![Download installer](https://img.shields.io/github/v/release/Chidaruma696/Cirno?label=%E2%AC%87%EF%B8%8F%20DOWNLOAD%20INSTALLER&style=for-the-badge&color=2e7de9)](https://github.com/Chidaruma696/Cirno/releases/latest)

<br/>

*Drag the PDFs, press Convert, done · everything on your machine · nothing uploaded anywhere*

</div>

---

> [!IMPORTANT]
> **Cirno sends nothing anywhere.** It reads the PDFs on your machine and writes the Excel files where you tell it to.
> Statements contain personal data: the repository ignores `*.pdf` and `*.xlsx` so they never end up in git by accident.

<br/>

## 📲 Download

1. Open the [latest release](https://github.com/Chidaruma696/Cirno/releases/latest) and grab `Cirno-x.y.z-setup.exe`.
2. Run it. It installs per user without asking for administrator rights (or for all users, if you choose so). No Python or anything else required.
3. Open Cirno from the Start menu. Later versions install on top.

<br/>

## ❄️ What it does

| Input | Output | How |
| --- | --- | --- |
| Supplier account statements in PDF (`EdoCta-…pdf`, the common SAP layout with RESUMEN / Movimientos / Saldo final / CIFRAS CONTROL), one or many | One `.xlsx` per PDF, or a single workbook with everything | Drag the PDFs onto the window and press **CONVERTIR** |

Every workbook has four sheets, with dates and amounts as real values (not text), filters and a frozen header:

- **Resumen**: account, customer, company, period, issue date and the RESUMEN block (opening balance, purchases, charges, payments, allowances, cancellations, closing balance).
- **Movimientos**: date, type (opening balance / charge / credit / application), reference, assignment, charges, credits, running balance and the application detail of each payment, just like the PDF.
- **Aplicaciones**: the application detail as a flat table (payment date and reference, applied amount, credit note, applied document), ready for pivot tables.
- **Saldo final**: outstanding documents with due date, charge, credit, balance and description.

The PDF's **CIFRAS CONTROL** rows are copied as totals and, on top of that, Cirno adds up charges, credits and applied payments on its own and warns if anything does not match (**Avisos** sheet). Amounts with a trailing dash (`25,000.42-`) become negative numbers.

Given a PDF in some other format, it does not stay silent: it dumps whatever tables it finds (or the text line by line) into an Excel file and flags it as a warning.

<br/>

## ⚙️ How it works

The PDF has no real tables, only text placed at coordinates. Cirno reads every word with its position ([pdfplumber](https://github.com/jsvine/pdfplumber)), groups words into rows, assigns each word to a column by its horizontal position (calibrated with several statements) and detects sections by their titles: `RESUMEN`, `Movimientos del periodo`, `Detalles de Saldo Final`, `CIFRAS CONTROL`. It does not rely on the header row, since some PDFs do not return it to the extractor. A row with a date is a movement; a row without a date but with an amount under "Pago" is an application of the previous movement. Tables spanning pages are followed seamlessly.

Excel files are written by [openpyxl](https://openpyxl.readthedocs.io/). The window is Qt ([PySide6](https://doc.qt.io/qtforpython-6/)) with the Komi look: paper and ink, square corners, hard shadows, ice palette. The interface is in Spanish.

<br/>

## ⌨️ Command line

The same executable (or `python -m cirno`) takes arguments:

```
Cirno.exe EdoCta-1.pdf EdoCta-2.pdf          # opens the window with those PDFs preloaded
Cirno.exe --cli C:\statements\ -o C:\out     # converts every PDF in the folder, no window
Cirno.exe --cli *.pdf --unir -n quarter.xlsx
```

| Option | Effect |
| --- | --- |
| `-o FOLDER` | Output folder (default: next to each PDF) |
| `-u`, `--unir` | One workbook with every statement; each row carries file, account and period |
| `-n FILE.xlsx` | Name of the merged workbook |
| `--cli` | Convert without opening the window |

<br/>

## 🛠️ Build

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

<br/>

## 🗺️ Roadmap

- [ ] More statement and invoice formats (each format is a module of columns and titles).
- [ ] CSV export.
- [ ] Dark theme.

<br/>

## ⚖️ Legal

Cirno is free software under the [Apache 2.0](LICENSE) license. Third-party components and their licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Touhou Project and its characters belong to Team Shanghai Alice (ZUN); unofficial fan work made under their guidelines for derivative works, with no affiliation or endorsement.

<br/>

<div align="center">

チルノ

</div>
