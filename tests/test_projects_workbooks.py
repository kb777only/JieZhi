from pathlib import Path
from zipfile import ZipFile
from openpyxl import Workbook
from jiezhi.attachments import extract
from jiezhi.projects import Projects


def test_xlsx_sheets_cells_formulas_and_limits(tmp_path):
    book=Workbook();sheet=book.active;sheet.title='Budget';sheet.append(['Item','Cost']);sheet.append(['Launch',742]);sheet['B3']='=SUM(B2:B2)'
    book.create_sheet('Notes')['A1']='Willow'
    path=tmp_path/'budget.xlsx';book.save(path)
    doc=extract(path)
    assert '[Sheet: Budget]' in doc['text'] and 'B2=742' in doc['text']
    assert '=SUM(B2:B2)' in doc['text'] and 'cached value: unavailable' in doc['text']
    assert '[Sheet: Notes]' in doc['text']


def test_ods_repeated_rows_are_bounded(tmp_path):
    path=tmp_path/'budget.ods'
    xml='''<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet><table:table table:name="Budget"><table:table-row table:number-rows-repeated="999999999"><table:table-cell office:value="742"><text:p>Launch</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet></office:body></office:document-content>'''
    with ZipFile(path,'w') as z:z.writestr('content.xml',xml)
    doc=extract(path);assert 'Launch' in doc['text'] and doc['truncated'] and len(doc['text'])<1000


def test_project_context_persistence_and_exclusions(tmp_path):
    store=Projects(tmp_path/'projects');p=store.create('Launch planning')
    root=tmp_path/'files';root.mkdir();(root/'brief.md').write_text('The launch code is WILLOW-742.')
    (root/'.env').write_text('secret');(root/'linked.md').symlink_to(root/'brief.md')
    (root/'node_modules').mkdir();(root/'node_modules'/'junk.md').write_text('Ignore')
    p['folders']=[str(root)];p['instructions']='Focus on launch readiness.';store.save(p)
    restored=store.all()[0];assert restored['instructions']==p['instructions']
    assert [f['name'] for f in store.index(p)]==['brief.md']
    assert 'WILLOW-742' in store.references(p,'launch code')[0]['text']
    store.remove(p);assert (root/'brief.md').exists()
