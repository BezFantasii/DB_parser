from pathlib import Path
import re
from html import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/pdf/technical_specification.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
for name, font in [('TimesRU','times.ttf'), ('TimesRU-Bold','timesbd.ttf'), ('TimesRU-Italic','timesi.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / font)))
pdfmetrics.registerFontFamily('TimesRU', normal='TimesRU', bold='TimesRU-Bold', italic='TimesRU-Italic', boldItalic='TimesRU-Bold')

styles = {
    'body': ParagraphStyle('body', fontName='TimesRU', fontSize=11, leading=14.5, spaceAfter=6, alignment=TA_JUSTIFY, allowWidows=0, allowOrphans=0),
    'h1': ParagraphStyle('h1', fontName='TimesRU-Bold', fontSize=14, leading=18, spaceBefore=12, spaceAfter=7, keepWithNext=True),
    'h2': ParagraphStyle('h2', fontName='TimesRU-Bold', fontSize=12, leading=16, spaceBefore=10, spaceAfter=6, keepWithNext=True),
    'title': ParagraphStyle('title', fontName='TimesRU-Bold', fontSize=24, leading=30, alignment=TA_CENTER, spaceAfter=20),
    'subtitle': ParagraphStyle('subtitle', fontName='TimesRU-Bold', fontSize=18, leading=24, alignment=TA_CENTER, spaceAfter=22),
    'cell': ParagraphStyle('cell', fontName='TimesRU', fontSize=9.5, leading=12, spaceAfter=0),
    'thead': ParagraphStyle('thead', fontName='TimesRU-Bold', fontSize=9.5, leading=12, spaceAfter=0),
    'bullet': ParagraphStyle('bullet', fontName='TimesRU', fontSize=11, leading=14.5, leftIndent=12, firstLineIndent=-10, spaceAfter=4),
    'toc': ParagraphStyle('toc', fontName='TimesRU', fontSize=11, leading=15, spaceBefore=3, leftIndent=0),
}

def markup(text):
    text = escape(text)
    return re.sub(r'`([^`]+)`', r'<b>\1</b>', text)

class SpecDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, 'toc_entry', False):
            title = flowable.getPlainText()
            key = f'section-{len(self.canv._doc._outlines._entries)}' if False else 'section-' + str(self.page) + '-' + str(len(title))
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=0, closed=False)
            self.notify('TOCEntry', (0, title, self.page, key))

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('TimesRU', 9)
    canvas.setFillColor(colors.HexColor('#444444'))
    canvas.drawRightString(A4[0]-52, 27, str(doc.page))
    canvas.restoreState()

doc = SpecDoc(str(OUT), pagesize=A4, leftMargin=60, rightMargin=52, topMargin=48, bottomMargin=48,
              title='Техническое задание на систему поиска аналогов товаров', author='', subject='Учебный проект Python PostgreSQL SQL')
doc.addPageTemplates(PageTemplate(id='main', frames=[Frame(60,48,A4[0]-112,A4[1]-96, leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)], onPage=footer))
lines = (ROOT / 'docs/technical_specification.md').read_text(encoding='utf-8').splitlines()
start = next(i for i, line in enumerate(lines) if line == '## 1 Назначение и объём проекта')
styles['title'].fontSize = 18
styles['title'].leading = 22
styles['title'].spaceAfter = 8
styles['subtitle'].fontSize = 14
styles['subtitle'].leading = 18
styles['subtitle'].spaceAfter = 10
story = [Paragraph('Техническое задание', styles['title']),
         Paragraph('Система поиска аналогов товаров на маркетплейсах', styles['subtitle'])]
for line in lines[3:start]:
    if not line.strip():
        continue
    if line.startswith('### '):
        story.append(Paragraph(line[4:], styles['h2']))
    else:
        story.append(Paragraph(markup(line), styles['body']))

i = start
while i < len(lines):
    line = lines[i]
    if not line.strip():
        i += 1
        continue
    if line.startswith('## '):
        para = Paragraph(markup(line[3:]), styles['h1'])
        para.toc_entry = True
        story.append(para)
    elif line.startswith('### '):
        story.append(Paragraph(markup(line[4:]), styles['h2']))
    elif line.startswith('|'):
        raw_rows = []
        while i < len(lines) and lines[i].startswith('|'):
            if not re.fullmatch(r'[| :\-]+', lines[i]):
                raw_rows.append([cell.strip() for cell in lines[i].strip('|').split('|')])
            i += 1
        cols = len(raw_rows[0])
        width = A4[0]-112
        if cols == 2:
            widths = [width*0.34, width*0.66]
        elif cols == 3:
            widths = [width*0.27, width*0.42, width*0.31]
            if raw_rows[0][0] == 'Код':
                widths = [width*0.12, width*0.29, width*0.59]
        else:
            widths = [width/cols]*cols
        rows = [[Paragraph(markup(c), styles['thead'] if idx == 0 else styles['cell']) for c in row] for idx,row in enumerate(raw_rows)]
        table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#D9D9D9')),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8EDF2')),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ]))
        story += [table, Spacer(1,8)]
        continue
    elif line.startswith('- '):
        story.append(Paragraph('• ' + markup(line[2:]), styles['bullet']))
    elif re.match(r'^\d+\. ', line):
        story.append(Paragraph(markup(line), styles['bullet']))
    else:
        story.append(Paragraph(markup(line), styles['body']))
    i += 1

doc.multiBuild(story)
reader = PdfReader(OUT)
text = '\n'.join(p.extract_text() or '' for p in reader.pages)
for required in ['Q10','PostgreSQL','psycopg','NULL','pg_dump','Преподаватель']:
    assert required in text, required
assert 3 <= len(reader.pages) <= 6
print(f'PDF created: {len(reader.pages)} pages, {OUT.stat().st_size} bytes')
for number,page in enumerate(reader.pages,1):
    print(number, len(page.extract_text() or ''))
