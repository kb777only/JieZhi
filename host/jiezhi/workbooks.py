"""Bounded workbook extraction. Never executes macros or recalculates formulas."""
from pathlib import Path
from zipfile import ZipFile

LIMIT = 200_000


def workbook_text(path: Path):
    parts = []; count = 0; truncated = False
    def add(text):
        nonlocal count, truncated
        if count + len(text) > LIMIT:
            parts.append(text[:max(0, LIMIT - count)]); truncated = True; count = LIMIT
            return False
        parts.append(text); count += len(text)
        return True
    suffix = path.suffix.lower()
    if suffix in {'.xlsx', '.xlsm', '.ods'}:
        with ZipFile(path) as archive:
            if len(archive.infolist()) > 10000 or sum(i.file_size for i in archive.infolist()) > 64 * 1024**2:
                raise ValueError('This workbook expands beyond the 64 MiB extraction limit. Export the needed sheets as CSV.')
    add('Workbook reference. Formulas are shown as text; cached values may be stale. Macros are never executed.\n')
    if suffix in {'.xlsx', '.xlsm'}:
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=False, keep_links=False)
        values = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            for sheet in book.worksheets[:30]:
                if not add(f'\n[Sheet: {sheet.title}]\n'): break
                if sheet.max_row and sheet.max_row > 10000 or sheet.max_column and sheet.max_column > 100:
                    truncated = True
                rows = sheet.iter_rows(max_row=min(sheet.max_row or 10000, 10000), max_col=min(sheet.max_column or 100, 100))
                cached = values[sheet.title].iter_rows(max_row=min(sheet.max_row or 10000, 10000), max_col=min(sheet.max_column or 100, 100))
                for row, cached_row in zip(rows, cached):
                    cells = []
                    for cell, cache in zip(row, cached_row):
                        if cell.value is not None:
                            value = str(cell.value)
                            if cell.data_type == 'f': value += f' [cached value: {cache.value if cache.value is not None else "unavailable"}]'
                            cells.append(f'{cell.coordinate}={value}')
                    if cells and not add(' | '.join(cells) + '\n'): break
                if count >= LIMIT: break
            truncated |= len(book.worksheets) > 30
        finally:
            book.close(); values.close()
    elif suffix == '.xls':
        import xlrd
        book = xlrd.open_workbook(str(path), on_demand=True)
        try:
            for sheet in book.sheets()[:30]:
                if not add(f'\n[Sheet: {sheet.name}] (stored values; XLS formulas are not exposed)\n'): break
                truncated |= sheet.nrows > 10000 or sheet.ncols > 100
                for r in range(min(sheet.nrows, 10000)):
                    cells = []
                    for c in range(min(sheet.ncols,100)):
                        cell=sheet.cell(r,c); value=cell.value
                        if cell.ctype==xlrd.XL_CELL_DATE: value=xlrd.xldate_as_datetime(value,book.datemode).isoformat()
                        if value != '': cells.append(f'R{r+1}C{c+1}={value}')
                    if cells and not add(' | '.join(cells)+'\n'): break
                if count >= LIMIT: break
            truncated |= book.nsheets > 30
        finally: book.release_resources()
    elif suffix == '.ods':
        from defusedxml.ElementTree import fromstring
        table = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'
        office = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
        with ZipFile(path) as archive: root = fromstring(archive.read('content.xml'))
        sheets = root.findall('.//' + table + 'table')
        for sheet in sheets[:30]:
            if not add(f'\n[Sheet: {sheet.get(table+"name", "Sheet")}]\n'): break
            row_number = 1
            for row in sheet.findall(table+'table-row'):
                repeat = int(row.get(table+'number-rows-repeated', '1'))
                column = 1; cells = []
                for cell in row:
                    if column > 100: truncated = True; break
                    value = ''.join(cell.itertext()).strip() or cell.get(office+'value', cell.get(office+'date-value', cell.get(office+'boolean-value', cell.get(office+'string-value', ''))))
                    formula = cell.get(table+'formula')
                    if formula: value = f'{formula} [cached value: {value or "unavailable"}]'
                    n = int(cell.get(table+'number-columns-repeated', '1'))
                    if value: cells.append(f'C{column}' + (f'..C{column+n-1}' if n>1 else '') + '=' + value)
                    column += n
                if cells and not add(f'R{row_number}' + (f'..R{row_number+repeat-1}' if repeat>1 else '') + ': ' + ' | '.join(cells)+'\n'): break
                row_number += repeat
                if row_number > 10000: truncated = True; break
            if count >= LIMIT: break
        truncated |= len(sheets) > 30
    else: raise ValueError('Unsupported workbook. Use XLSX, XLSM, XLS, ODS or CSV.')
    return ''.join(parts), truncated
