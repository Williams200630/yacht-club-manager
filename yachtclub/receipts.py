from __future__ import annotations

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle

from .config import ROOT


def create_receipt(data,destination=None):
    folder=ROOT/'receipts';folder.mkdir(exist_ok=True)
    destination=Path(destination) if destination else folder/f"{data['receipt_number']}.pdf"
    destination.parent.mkdir(parents=True,exist_ok=True)
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    font_bold=Path('C:/Windows/Fonts/arialbd.ttf')
    if font_path.exists():
        pdfmetrics.registerFont(TTFont('YCM',str(font_path)))
        if font_bold.exists():pdfmetrics.registerFont(TTFont('YCMBold',str(font_bold)))
        face='YCM';bold='YCMBold' if font_bold.exists() else 'YCM'
    else:face='Helvetica';bold='Helvetica-Bold'
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReceiptTitle',parent=styles['Title'],fontName=bold,textColor=colors.HexColor('#143c5b'),fontSize=19,leading=23))
    styles.add(ParagraphStyle(name='SmallLocal',parent=styles['Normal'],fontName=face,fontSize=9,leading=13))
    story=[Paragraph('YACHT CLUB MANAGER',styles['ReceiptTitle']),Paragraph('Учебная электронная квитанция',styles['Heading2']),Spacer(1,4*mm)]
    if not data.get('is_test'):story.append(Paragraph('Подтверждение оплаты',styles['Heading2']))
    else:story.append(Paragraph('ДЕМО-ОПЛАТА · НЕ ЯВЛЯЕТСЯ ФИСКАЛЬНЫМ ЧЕКОМ',styles['Heading3']))
    rows=[
      ['Номер квитанции',str(data.get('receipt_number',''))],
      ['Платёж',f"№ {data.get('payment_id','')} · {data.get('method','')}"] ,
      ['Дата оплаты',str(data.get('confirmed_at') or data.get('issued_at') or '')],
      ['Клиент',f"{data.get('first_name','')} {data.get('last_name','')}"] ,
      ['Email',str(data.get('email',''))],['Яхта',str(data.get('boat_name',''))],
      ['Период',f"{data.get('start_at','')} — {data.get('end_at','')}"] ,
      ['Сумма платежа',f"{float(data.get('amount') or data.get('total_amount') or 0):,.2f} ₽"],
      ['Статус',str(data.get('status','Подтверждён'))]
    ]
    table=Table([[Paragraph(str(k),ParagraphStyle('k',fontName=bold,fontSize=9)),Paragraph(str(v),styles['SmallLocal'])] for k,v in rows],colWidths=[48*mm,115*mm])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#edf4f8')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#d4e0e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.extend([table,Spacer(1,9*mm),Paragraph('Квитанция сформирована приложением Yacht Club Manager. Для реальной оплаты используйте реквизиты клуба или подключённого сертифицированного провайдера.',styles['SmallLocal'])])
    doc=SimpleDocTemplate(str(destination),pagesize=A4,rightMargin=22*mm,leftMargin=22*mm,topMargin=20*mm,bottomMargin=20*mm,title='Yacht Club Manager Receipt')
    doc.build(story)
    return destination
