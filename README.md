[🇪🇸 Español](README.es.md)

<div align="center">
  <br/>
  <img src="cirno/assets/cirno.png" width="180" alt="Cirno icon" />

# Cirno

**チルノ · A PDF suite for the office: merge, reorder and edit pages, pull tables and data into Excel, and do to a workbook whatever you ask in plain words. No AI.**

<br/>

![Windows 10/11](https://img.shields.io/badge/windows-10%2F11%20x64-0078d4?style=for-the-badge&logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/qt-pyside6-41cd52?style=for-the-badge&logo=qt&logoColor=white)
![Apache 2.0 license](https://img.shields.io/badge/license-Apache%202.0-1b150d?style=for-the-badge)

<br/>

[![Download installer](https://img.shields.io/github/v/release/Chidaruma696/Cirno?label=%E2%AC%87%EF%B8%8F%20DOWNLOAD%20INSTALLER&style=for-the-badge&color=2e7de9)](https://github.com/Chidaruma696/Cirno/releases/latest)

<br/>

*Drag the files in, pick what you want, done · everything on your machine · originals are never touched*

</div>

---

> [!IMPORTANT]
> **Cirno sends nothing anywhere.** It reads the files on your machine and writes the results where you tell it to; the only thing it asks the network is whether there is a newer version.
> The repository ignores `*.pdf` and `*.xlsx` so office documents never end up in git by accident.

<br/>

## 📲 Download

1. Open the [latest release](https://github.com/Chidaruma696/Cirno/releases/latest) and grab `Cirno-x.y.z-setup.exe`.
2. Run it. It installs per user without asking for administrator rights (or for all users, if you choose so). No Python or anything else required.
3. Open Cirno from the Start menu.

**Updates arrive on their own.** On start, Cirno asks GitHub whether there is a newer release; if so, a notice shows at the bottom right. Clicking it downloads the installer, checks it against the SHA-256 published next to it, closes Cirno, installs and opens it again. Nothing is ever installed without you asking, and the check can be turned off under *Ayuda*.

<br/>

## ❄️ What it does

Three tabs, one per job. Nothing uses AI or the internet: it is all rules running on your machine. The interface is in Spanish.

| Tab | What for | How |
| --- | --- | --- |
| **Organizar y editar PDF** | Merge several PDFs (and images), reorder the pages, edit them, number them, protect them, split them into several files | Drag the files in, move the pages with the mouse, double-click one to edit it, then **Guardar PDF** |
| **Extraer datos** | Pull tables and loose data into Excel, embedded images or whole pages into PNG or JPG, and the text into a `.txt` | Drag the PDFs in, review what Cirno found in each and press **Extraer** |
| **Excel en palabras** | Paint, sort, group, remove duplicates, sum by group… by saying so: *«agrupa por Cliente y pinta de rojo los PENDIENTE»* | Pick the workbook, write the sentence, review what it understood and press **Aplicar** |

### Organizing and editing PDFs

Every page is a thumbnail in a grid. Select with the mouse (Ctrl and Shift for several) and drag them into place; more files can be dropped in between. Everything has undo and redo. Images come in as one more page, with JPEGs embedded as they are. Merging keeps each PDF's bookmarks.

**The editor** (double-click a page) lets you:

- **Write** text anywhere, with typeface, size, bold, italic and colour.
- **Fix text that is already there**: click it, Cirno covers it with the background colour, picks up its size, colour and typeface, and leaves it open for you to retype.
- **Highlight** (the highlight snaps to the text lines), **cover**, frame, lines, arrows and **draw** a signature by hand.
- Paste **images** (a stamp, a scanned signature), move them, resize them and copy them to every page.
- **Crop** the page, or all of them alike.

**Covering is erasing.** What lies under a cover is not just hidden: the glyphs are removed from the PDF content, and in a scan the area is painted inside the image itself. It cannot be searched, copied or uncovered. (Text a PDF keeps inside form XObjects, which is rare, stays covered but not erased.)

**Tools**: page numbers ("Página 3 de 12", wherever you like), watermark, interleaving fronts and backs of a two-pass scan, reversing. **Select**: odd, even, landscape, edited and **blank pages**. **Split**: one PDF per page, every so many, or **one PDF per document** (it cuts where the text says "Página 1 de N", for batches of invoices or receipts). On saving you can set a **password**, **shrink the file** (downsamples scans and photos) and fill in title and author.

The original file is never modified: Cirno refuses to save over it.

### Extracting data

Drop a PDF and Cirno looks inside, shows what it has and says what it looks like (invoice, quote, order, stock ledger, statement…):

- **Tables**, ruled or not. Drawn tables are rebuilt from their lines; the rest are inferred from text alignment. Two tables in a row with different headers come out separate; one running for twenty pages, as a single table with its header once; if it goes by sections (a title and the same header repeated), the title becomes a column. Cells that wrap are joined to their row, even when vertically centred. The line above names the sheet.
- **Checked totals**: if a table has a totals row, Cirno adds up the rows and says whether it matches what the PDF states.
- **Loose data**: whatever is not in a table (`Cliente: …`, document numbers, dates, subtotal, VAT and total, Mexican RFC, CURP, CLABE with its check digit, tax UUID, e-mails, phones) goes to a «Datos» sheet.
- **Supplier account statements** (`EdoCta-…pdf`, the common SAP layout with RESUMEN / Movimientos / Saldo final / CIFRAS CONTROL), with their own reader and control-figure cross-checks.
- **Embedded images**, **whole pages as images** at the resolution you choose, and **text**.

In the workbook each column is understood as a whole: amounts are numbers, dates are dates, `168.9 kg` is the number 168.9 with "kg" in its format (looks the same, can be summed), and a column with zero-padded codes stays text throughout. A scan with no text is reported as such: Cirno does no OCR.

### Excel in words

You write what you want, several things at once, and Cirno turns it into steps you can review and untick before applying. Everything goes into a copy (`<name> - Cirno.xlsx`).

| You say | It does |
| --- | --- |
| *«rojo las filas donde Estado sea PENDIENTE; en negrita los Importes mayores de 50 mil»* | Live Excel conditional formatting |
| *«busca los valores iguales de Cliente, agrúpalos»* | Marks duplicates and brings equal rows together, with a rule between groups |
| *«ordena del más reciente al más antiguo»* | Sorts by the date column |
| *«quita los repetidos de Folio»*, *«deja solo los PENDIENTE»* | Removes rows |
| *«suma el Importe por Cliente»*, *«cuántos pendientes hay por cliente»* | A «Resumen» sheet with `SUMIF`, `COUNTIFS`… formulas |
| *«pon totales»*, *«añade Importe con IVA»*, *«Importe como moneda»*, *«pon filtros»* | Totals row, formula column, number format, filters and frozen header |

There is no model behind it: it is an internal recipe book with its keywords. Whatever matches no recipe is not guessed: Cirno says so and suggests the closest ones. The **Ideas** button shows the whole recipe book and lets you search it.

<br/>

## ⚙️ How it works

- **Pages.** [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (PDFium) renders thumbnails; [pikepdf](https://github.com/pikepdf/pikepdf) (qpdf) writes the final PDF by copying pages as they are. The document you build is only a list of (file, page, rotation, marks, crop) until the moment you save.
- **Editing.** What you add is written as ordinary page content (text in the base fonts, rectangles, images), not as annotations: it looks the same in any viewer and in print. `cirno/pdf/borrar.py` walks the content tracking every glyph's position (matrices, font, spacing) and removes the ones under a cover.
- **Tables.** [pdfplumber](https://github.com/jsvine/pdfplumber) gives every word with its position. `cirno/extraccion/tablas.py` groups them into lines, splits each line at wide gaps, recognises header rows and derives the columns from the blank "rivers" the rows share.
- **Excel.** `cirno/formato/` holds the interpreter of [Sunny](https://github.com/Chidaruma696/Sunny) for painting and the recipe book (`recetas.py`) for the rest, all written with [openpyxl](https://openpyxl.readthedocs.io/).

The window is Qt ([PySide6](https://doc.qt.io/qtforpython-6/)) with the system look, light or dark as you have it.

<br/>

## ⌨️ Command line

The same executable (or `python -m cirno`) takes arguments:

```
Cirno.exe report.pdf                          # opens the window with that PDF under «Extraer datos»
Cirno.exe sales.xlsx                          # opens the window with that workbook under «Formato de Excel»
Cirno.exe --cli C:\pdf\ -o C:\out             # extracts every PDF in the folder to Excel, no window
Cirno.exe --cli *.pdf --unir -n quarter.xlsx
Cirno.exe --cli scan.pdf --sin-excel --paginas --formato jpg --ppp 300
Cirno.exe --unir-pdf all.pdf a.pdf b.pdf c.pdf
```

| Option | Effect |
| --- | --- |
| `-o FOLDER` | Output folder (by default, next to each PDF) |
| `-u`, `--unir` | A single workbook with every statement; each row carries file, account and period |
| `-n FILE.xlsx` | Name of the merged workbook |
| `--imagenes` | Also extract the embedded images |
| `--paginas` | Also export each page as an image |
| `--texto` | Also write the text to a `.txt` |
| `--sin-excel` | Do not write the workbook |
| `--formato png\|jpg`, `--ppp N` | Image format and page resolution |
| `--unir-pdf OUT.pdf` | Merge the given PDFs, in that order, into one |

Page editing and «Excel en palabras» are done from the window.
| `--cli` | Work without opening the window |

<br/>

## 🛠️ Build

You need Python 3.11 or later and, for the installer, [Inno Setup 6](https://jrsoftware.org/isdl.php).

```powershell
git clone https://github.com/Chidaruma696/Cirno.git
cd Cirno
.\build.ps1                  # .venv + dependencies + PyInstaller + Inno Setup → dist\Cirno-X.Y.Z-setup.exe (+ .sha256)
.\build.ps1 -SinInstalador   # only dist\Cirno\Cirno.exe
.\build.ps1 -Probar          # the tests
```

To develop without building:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m cirno
.\.venv\Scripts\python -m pytest
```

Layout:

```
cirno/pdf/render.py          Open PDFs and render pages (PDFium)
cirno/pdf/documento.py       The page list: move, rotate, duplicate, remove, undo
cirno/pdf/marcas.py          What is added to a page: text, boxes, lines, strokes, images
cirno/pdf/marcas_pdf.py      Write the marks and the crop into the PDF
cirno/pdf/borrar.py          Really erase the text and image under a cover
cirno/pdf/guardar.py         Write the PDF: merge, split, password, shrink (pikepdf)
cirno/extraccion/tablas.py   Find tables, headers, sections, wrapped cells, totals
cirno/extraccion/datos.py    Loose data (label: value, RFC, CLABE…) and document type
cirno/extraccion/valores.py  Understand cells and columns: numbers, dates, units, codes
cirno/extraccion/analisis.py What a PDF holds
cirno/extraccion/exportar.py Typed Excel, PNG, JPG, text
cirno/parser.py              Supplier statements (columns by position, validation)
cirno/excel.py               The workbook of a statement
cirno/convertir.py           Batch orchestration; used by the window and the command line
cirno/formato/               Excel in words: rules, interpreter, workbook and recipe book
cirno/updater.py             Updates from GitHub releases, with SHA-256
cirno/gui/                   PySide6 window: organise, editor, extract, format
cirno/cli.py                 Arguments and entry point
tests/                       pytest
cirno.spec                   PyInstaller (folder, no console)
installer/Cirno.iss          Inno Setup
build.ps1                    All of the above in one step
```

<br/>

## 🗺️ Roadmap

- [ ] OCR for scans.
- [ ] Writing with any system font (today: Arial/Helvetica, Times and Courier, Latin alphabet).
- [ ] Filling in forms; scaling and placing several pages on one sheet.
- [ ] More statement and invoice formats (each format is a module of columns and titles).
- [ ] More Excel recipes (send the sentences it does not understand).

<br/>

## ⚖️ Legal

Cirno is free software under the [Apache 2.0](LICENSE) license. Third-party components and their licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The «Organizar PDF» tab takes its idea from [PDF Arranger](https://github.com/pdfarranger/pdfarranger); Cirno contains none of its code.

Touhou Project and its characters belong to Team Shanghai Alice (ZUN); unofficial fan work made under their guidelines for derivative works, with no affiliation or endorsement.

<br/>

<div align="center">

チルノ

</div>
