from __future__ import annotations

import csv
from html import escape as html_escape
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import subprocess
import sys
import traceback
from datetime import date,datetime,timedelta
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt,QDate,QDateTime,QThread,Signal,QTimer,QUrl
from PySide6.QtGui import QAction,QPixmap,QFont,QPainter,QColor,QPainterPath
from PySide6.QtWidgets import (
 QApplication,QMainWindow,QWidget,QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,
 QLabel,QPushButton,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QDateEdit,QDateTimeEdit,
 QCheckBox,QMessageBox,QFrame,QStackedWidget,QScrollArea,QTableWidget,QTableWidgetItem,QHeaderView,
 QAbstractItemView,QDialogButtonBox,QFileDialog,QTabWidget,QGroupBox,QProgressBar,QPlainTextEdit,
 QSplitter,QListWidget,QListWidgetItem,QRadioButton,QButtonGroup,QSizePolicy,QInputDialog,QToolButton
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

from yachtclub.config import ROOT,load_settings
from yachtclub.db import Db,connect_with_autostart
from yachtclub.service import YachtService
from yachtclub.weather import fetch_weather,assess,weather_condition
from yachtclub.receipts import create_receipt

BOAT_INTERIOR_GALLERY={
 'Парусная яхта':[(f'assets/boats/interiors/interior_sailing_yacht_{i:02d}.jpg',f'Внутри парусной яхты · фото {i}') for i in range(1,4)],
 'Моторная яхта':[(f'assets/boats/interiors/interior_motor_yacht_{i:02d}.jpg',f'Внутри моторной яхты · фото {i}') for i in range(1,4)],
 'Катер':[(f'assets/boats/interiors/interior_speedboat_{i:02d}.jpg',f'Внутри катера · фото {i}') for i in range(1,4)],
 'Катамаран':[(f'assets/boats/interiors/interior_catamaran_{i:02d}.jpg',f'Внутри катамарана · фото {i}') for i in range(1,4)],
 'Премиум яхта':[(f'assets/boats/interiors/interior_premium_yacht_{i:02d}.jpg',f'Внутри премиум яхты · фото {i}') for i in range(1,4)],
}


def configure_logging():
    logger=logging.getLogger('yachtclub');logger.setLevel(logging.INFO)
    if logger.handlers:return
    try:
        log_dir=ROOT/'logs';log_dir.mkdir(exist_ok=True)
        handler=RotatingFileHandler(log_dir/'yachtclub.log',maxBytes=2_000_000,backupCount=3,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.StreamHandler())


APP_STYLE="""
QWidget{background:#f1f7fa;color:#17384f;font-family:'Segoe UI';font-size:10pt}
QMainWindow{background:#eff7fa}
QLabel{background:transparent}
QFrame#Topbar{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffffff,stop:1 #e8f5f7);border-bottom:1px solid #d4e6ec}
QFrame#Sidebar{background:#12344f}
QLabel#Brand{color:#12344f;font-size:18pt;font-weight:800}
QLabel#Title{color:#12344f;font-size:22pt;font-weight:750}
QLabel#Subtitle{color:#71899b;font-size:10pt}
QLabel#HeroTitle{color:white;background:transparent;font-size:29pt;font-weight:800}
QLabel#HeroSub{color:#e0edf3;background:transparent;font-size:12pt}
QLabel#AboutHeading{color:#153b55;font-size:18pt;font-weight:750;padding-top:8px}
QLabel#AboutBody{color:#294e67;font-size:12pt;line-height:1.5;padding-bottom:10px}
QFrame#Card,QFrame#MetricCard,QGroupBox{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #f2fafb);border:1px solid #d8e8ed;border-radius:14px}
QFrame#MetricCard{padding:10px}
QLabel#Metric{color:#148397;font-size:23pt;font-weight:750}
QLabel#MetricCaption{color:#71899b;font-size:9pt}
QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2299a6,stop:1 #117788);color:white;border:0;border-radius:9px;padding:9px 15px;font-weight:600}
QPushButton:hover{background:#0d6979}
QPushButton#Secondary{background:#e7f1f5;color:#244e69}
QPushButton#Secondary:hover{background:#d9e9ef}
QPushButton#Nav{color:#d3e3eb;background:transparent;text-align:left;border-radius:8px;padding:11px 13px}
QPushButton#Nav:hover,QPushButton#Nav[active="true"]{background:#205372;color:white}
QPushButton#ClientNav{color:#244e69;background:transparent;border-radius:8px;padding:10px 12px}
QPushButton#ClientNav:hover,QPushButton#ClientNav[active="true"]{background:#e7f1f5;color:#12344f}
QPushButton#Link{background:transparent;color:#137f91;text-align:left;padding:3px}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QDateEdit,QDateTimeEdit,QTextEdit,QPlainTextEdit{
 background:#fff;border:1px solid #cbd9e2;border-radius:8px;padding:7px}
QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QDateEdit:focus,QDateTimeEdit:focus,QTextEdit:focus,QPlainTextEdit:focus{border:1px solid #319eaa}
QTableWidget{background:white;alternate-background-color:#f6f9fb;gridline-color:#e7edf1;border:1px solid #dce6ec}
QHeaderView::section{background:#eaf1f5;color:#294e67;padding:8px;border:0;font-weight:650}
QTabWidget::pane{border:1px solid #e0e8ed;border-radius:8px;background:#fff}
QTabBar::tab{padding:9px 15px;background:#eaf1f5;border-radius:6px;margin:3px}
QTabBar::tab:selected{background:#147f91;color:white}
QScrollArea{border:0;background:transparent}
QCheckBox{spacing:8px}
"""


def local_dt(qdt:QDateTime)->datetime:
    return qdt.toPython().astimezone()


def money(value):
    try:return f"{float(value or 0):,.0f} ₽".replace(',',' ')
    except (TypeError,ValueError):return "—"


def pretty(value):
    if value is None:return "—"
    if isinstance(value,datetime):return value.astimezone().strftime('%d.%m.%Y %H:%M') if value.tzinfo else value.strftime('%d.%m.%Y %H:%M')
    if isinstance(value,date):return value.strftime('%d.%m.%Y')
    if isinstance(value,Decimal):return f"{float(value):,.2f}".replace(',',' ')
    if isinstance(value,bool):return 'Да' if value else 'Нет'
    if isinstance(value,(list,tuple)):return ', '.join(str(x) for x in value)
    if isinstance(value,dict):return json.dumps(value,ensure_ascii=False)
    labels={
        'client':'Клиент','admin':'Администратор','manager':'Менеджер',
        'available':'Свободна','reserved':'Забронирована','rented':'В аренде','maintenance':'Обслуживание','unavailable':'Недоступна',
        'pending':'Ожидает подтверждения','confirmed':'Подтверждена','awaiting_payment':'Ожидает оплаты','paid':'Оплачена','active':'Активна',
        'completed':'Завершена','rejected':'Отклонена','cancelled':'Отменена','expired':'Истёк срок оплаты',
        'created':'Создан','pending_confirmation':'Ожидает проверки','declined':'Отклонён','refunded':'Возвращён','partially_refunded':'Частично возвращён',
        'planned':'Запланировано','in_progress':'В работе','closed':'Закрыта','issued':'Выдана','returned':'Возвращена','inspection_required':'Нужен осмотр',
        'processed':'Обработан','approved':'Одобрено','insert':'Добавление','update':'Изменение','delete':'Удаление'
    }
    return labels.get(str(value),str(value))


def message_error(parent,title,exc):
    logging.getLogger('yachtclub').exception('%s',title)
    if isinstance(exc,(ValueError,PermissionError)):
        message=str(exc)
    else:
        message='Не удалось выполнить действие. Проверьте данные и повторите попытку. Техническая подробность записана в журнал приложения.'
    QMessageBox.critical(parent,title,message)


class HeroBanner(QFrame):
    def __init__(self,image_path,parent=None):
        super().__init__(parent);self._image=QPixmap(str(image_path));self.setMinimumHeight(330)
        self.setStyleSheet('QFrame{border-radius:20px}')

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        path=QPainterPath();path.addRoundedRect(self.rect(),20,20);painter.setClipPath(path)
        if not self._image.isNull():
            image=self._image.scaled(self.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)
            x=(self.width()-image.width())//2;y=(self.height()-image.height())//2
            painter.drawPixmap(x,y,image)
        else:painter.fillRect(self.rect(),QColor('#173d58'))
        painter.fillRect(self.rect(),QColor(8,31,49,112))
        super().paintEvent(event)


class BootWorker(QThread):
    finished_result=Signal(bool,str)
    def __init__(self,settings):super().__init__();self.settings=settings
    def run(self):
        ok,info=connect_with_autostart(self.settings)
        self.finished_result.emit(ok,info)


class WeatherWorker(QThread):
    result=Signal(object,object)
    def __init__(self,service,lat,lon):super().__init__();self.service=service;self.lat=lat;self.lon=lon
    def run(self):
        try:
            rules=self.service.db.rows("SELECT bt.name,r.warning_wind_speed,r.danger_wind_speed,r.warning_gust,r.danger_gust FROM safety_rules r JOIN boat_types bt USING(boat_type_id)")
            data=fetch_weather(self.lat,self.lon,rules)
            self.service.save_weather([data['current'],*data['hourly']])
            self.result.emit(data,None)
        except Exception as e:self.result.emit(None,e)


class EyeButton(QToolButton):
    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setPen(QColor('#52758a'));p.setBrush(Qt.NoBrush)
        path=QPainterPath();path.moveTo(4,13);path.cubicTo(9,5,17,5,22,13);path.cubicTo(17,21,9,21,4,13);p.drawPath(path)
        p.setBrush(QColor('#52758a'));p.drawEllipse(10,10,6,6)
        if not self.isChecked():p.drawLine(5,21,22,5)
        p.end()


class PasswordLineEdit(QLineEdit):
    """Password editor with a compact, non-destructive visibility toggle."""
    def __init__(self,parent=None):
        super().__init__(parent);self.setEchoMode(QLineEdit.Password);self.setTextMargins(0,0,34,0)
        self.eye=EyeButton(self);self.eye.setCheckable(True);self.eye.setCursor(Qt.PointingHandCursor)
        self.eye.setFocusPolicy(Qt.NoFocus);self.eye.setToolTip('Показать пароль');self.eye.setAccessibleName('Показать пароль')
        self.eye.setStyleSheet('QToolButton{border:0;background:transparent;padding:2px} QToolButton:hover{background:#e5f3f5;border-radius:8px}')
        self.eye.toggled.connect(self._set_password_visible)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.eye.setGeometry(self.width()-31,(self.height()-26)//2,26,26)
    def _set_password_visible(self,visible):
        self.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        label='Скрыть пароль' if visible else 'Показать пароль';self.eye.setToolTip(label);self.eye.setAccessibleName(label);self.eye.update()


class PortDialog(QDialog):
    def __init__(self,row=None,parent=None):
        super().__init__(parent);self.row=row or {};self.setWindowTitle('Порт');self.resize(560,640)
        root=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);host=QWidget();form=QFormLayout(host);self.fields={}
        for key,label in [('name','Название'),('address','Адрес'),('city','Город'),('latitude','Широта'),('longitude','Долгота'),('phone','Телефон'),('opening_hours','Режим работы')]:
            value=self.row.get(key);w=QLineEdit('' if value is None else str(value))
            if key in ('latitude','longitude'):w.setPlaceholderText('Например, 44.95; пусто — координаты неизвестны')
            self.fields[key]=w;form.addRow(label,w)
        self.description=QTextEdit(str(self.row.get('description','') or ''));self.description.setMaximumHeight(130);form.addRow('Описание',self.description)
        self.active=QCheckBox('Порт активен');self.active.setChecked(bool(self.row.get('is_active',True)));form.addRow(self.active)
        if self.row.get('is_demonstration'):form.addRow('Тип',QLabel('Демонстрационный порт; адрес и координаты не заданы'))
        scroll.setWidget(host);root.addWidget(scroll);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
    def values(self):
        data={k:w.text().strip() for k,w in self.fields.items()};data['description']=self.description.toPlainText().strip();data['is_active']=self.active.isChecked()
        for key in ('latitude','longitude'):data[key]=float(data[key].replace(',','.')) if data[key] else None
        if (data['latitude'] is None)!=(data['longitude'] is None):raise ValueError('Укажите обе координаты или оставьте обе пустыми.')
        if data['latitude'] is not None and not(-90<=data['latitude']<=90 and -180<=data['longitude']<=180):raise ValueError('Координаты должны быть в диапазоне широты ±90 и долготы ±180.')
        if not data['name']:raise ValueError('Укажите название порта.')
        return data


class _PortMapPage(QWebEnginePage):
    catalogRequested=Signal(int)
    portSelected=Signal(int)
    def acceptNavigationRequest(self,url,nav_type,is_main_frame):
        if url.scheme()=='ycm' and url.host()=='catalog':
            try:self.catalogRequested.emit(int(url.path().strip('/')))
            except ValueError:pass
            return False
        if url.scheme()=='ycm' and url.host()=='port':
            try:self.portSelected.emit(int(url.path().strip('/')))
            except ValueError:pass
            return False
        return super().acceptNavigationRequest(url,nav_type,is_main_frame)


class PortMapWidget(QWidget):
    catalogRequested=Signal(int)
    portSelected=Signal(int)
    def __init__(self,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.view=QWebEngineView(self);self.page=_PortMapPage(self.view);self.page.catalogRequested.connect(self.catalogRequested);self.page.portSelected.connect(self.portSelected);self.view.setPage(self.page);layout.addWidget(self.view,1)
    def reset_view(self):self.view.page().runJavaScript('window.resetPortMap && window.resetPortMap()')
    def show_port_details(self,port_id):self.view.page().runJavaScript(f'window.showPortDetails && window.showPortDetails({int(port_id)})')
    def set_ports(self,ports,selected_id=None):
        payload=json.dumps(ports,ensure_ascii=False,default=str).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        located=[p for p in ports if p.get('latitude') is not None and p.get('longitude') is not None]
        unlocated=[p for p in ports if p not in located]
        pins_html=''
        if located:
            min_x=min(float(p['longitude']) for p in located);max_x=max(float(p['longitude']) for p in located)
            min_y=min(float(p['latitude']) for p in located);max_y=max(float(p['latitude']) for p in located)
            span_x=max(max_x-min_x,.02);span_y=max(max_y-min_y,.02)
            pins=[]
            for p in located:
                x=8+(float(p['longitude'])-min_x)/span_x*84
                y=14+(max_y-float(p['latitude']))/span_y*68
                title=html_escape(str(p.get('name') or 'Порт'))
                city=html_escape(str(p.get('city') or p.get('address') or ''))
                free=p.get('free_count',0)
                summary=f'{city} · свободно мест: {free}' if city else f'Свободно мест: {free}'
                side=' right' if x>72 else ''
                color={'available':'#35a56e','partial':'#e1a23a','full':'#c84848','closed':'#87949d','unknown':'#287fbd'}.get(p.get('map_state'),'#287fbd')
                selected=' selected' if p['port_id']==selected_id else ''
                pins.append(f'<a class="static-pin{side}{selected}" href="ycm://port/{int(p["port_id"])}" title="{title} · {html_escape(str(p.get("map_state_ru") or ""))}" style="left:{x:.2f}%;top:{y:.2f}%;--pin-color:{color}"><span class="pin-dot">⚓</span><span class="pin-label"><b>{title}</b><small>{html_escape(summary)}</small></span></a>')
            pins_html=''.join(pins)
        else:
            pins_html='<div class="static-empty">Порты с координатами не найдены.</div>'
        if unlocated:
            names=', '.join(html_escape(str(p.get('name') or 'Порт')) for p in unlocated)
            pins_html+=f'<div class="static-unlocated"><b>Без координат:</b> {names}</div>'
        html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>*{box-sizing:border-box}body{margin:0;font:14px Segoe UI,Arial;color:#173c56;background:#eef7fb}.head{padding:12px 16px;background:linear-gradient(120deg,#dff5f7,#f8fcfd);border-bottom:1px solid #c9e0e9}.head b{font-size:16px}.hint{color:#55758a;margin-left:8px}#map{height:calc(100vh - 58px);min-height:430px;position:relative;overflow:hidden}#fallback{width:100%;height:100%;display:block;background:linear-gradient(160deg,#d4f1f2,#eaf5fa 52%,#c6e7ed)}#staticMap{position:absolute;inset:0;z-index:1;pointer-events:none;background:radial-gradient(ellipse at 25% 70%,#c1e4e6 0,transparent 42%),radial-gradient(ellipse at 75% 22%,#d3eef1 0,transparent 48%)}#leaflet{width:100%;height:100%;display:none;position:relative;z-index:2}.static-pin{position:absolute;display:flex;align-items:center;gap:7px;transform:translate(-8px,-50%);white-space:nowrap;text-decoration:none;pointer-events:auto;cursor:pointer}.static-pin.right{flex-direction:row-reverse;transform:translate(calc(-100% + 8px),-50%);text-align:right}.pin-dot{width:32px;height:32px;border:3px solid white;border-radius:50%;display:grid;place-items:center;background:var(--pin-color,#287fbd);color:white;box-shadow:0 2px 8px #173c5670;font-size:16px}.pin-label{display:grid;gap:2px;padding:6px 9px;border-radius:9px;background:#fffffff2;box-shadow:0 2px 12px #173c5640;font-size:13px;color:#173c56}.pin-label small{font-size:11px;color:#55758a}.static-empty,.static-unlocated{position:absolute;left:16px;top:16px;max-width:45%;padding:10px 13px;border-radius:10px;background:#fffffff2;box-shadow:0 2px 12px #173c5630}.static-unlocated{top:auto;bottom:16px}.key{position:absolute;z-index:500;right:15px;bottom:15px;background:#ffffffed;padding:10px 13px;border-radius:12px;box-shadow:0 4px 18px #24495a33;line-height:1.8}.port-card{min-width:220px}.port-card h3{margin:0 0 6px;color:#153b55}.port-card button{border:0;border-radius:8px;padding:8px 12px;background:#147f91;color:white;cursor:pointer}.state-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.demo{font-size:11px;color:#9a6417}</style></head><body>
<div class="head"><b>Карта портов</b><span id="hint" class="hint">Цвет маркера рассчитан по причалам и местам из базы.</span></div><div id="map"><canvas id="fallback"></canvas><div id="staticMap">__STATIC_MAP__</div><div id="leaflet"></div><div id="unmapped"></div><div class="key"><b>Состояние порта</b><br>🟢 Есть свободные места<br>🟠 Частично ограничен<br>🔴 Свободных мест нет<br>⚪ Закрыт　🔵 Нет данных</div></div>
<script>const ports=__PORTS__,selectedId=__SELECTED__,colors={free:'#35a56e',occupied:'#287fbd',reserved:'#e1a23a',unavailable:'#c84848',maintenance:'#8a687e',available:'#35a56e',partial:'#e1a23a',full:'#c84848',closed:'#87949d',unknown:'#287fbd'};const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const cvs=document.getElementById('fallback'),ctx=cvs.getContext('2d');let scale=1,dx=0,dy=0,drag=null,points=[],leafletMap=null,activePortId=selectedId;
window.resetPortMap=()=>{scale=1;dx=0;dy=0;draw();if(leafletMap){const cs=ports.filter(p=>p.latitude!=null&&p.longitude!=null);if(cs.length)leafletMap.fitBounds(cs.map(p=>[p.latitude,p.longitude]),{padding:[42,42],maxZoom:8})}};
function draw(){let r=cvs.getBoundingClientRect(),d=devicePixelRatio||1;cvs.width=r.width*d;cvs.height=r.height*d;ctx.setTransform(d,0,0,d,0,0);let w=r.width,h=r.height;ctx.clearRect(0,0,w,h);let g=ctx.createLinearGradient(0,0,w,h);g.addColorStop(0,'#d1eef0');g.addColorStop(.52,'#edf7fa');g.addColorStop(1,'#c7e7ed');ctx.fillStyle=g;ctx.fillRect(0,0,w,h);ctx.strokeStyle='#ffffff8c';for(let x=0;x<w;x+=70){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke()}for(let y=0;y<h;y+=70){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke()}let cs=ports.filter(p=>p.latitude!=null&&p.longitude!=null);if(!cs.length){ctx.fillStyle='#254d63';ctx.textAlign='center';ctx.font='600 17px Segoe UI';ctx.fillText('У портов в базе пока нет координат',w/2,h/2-8);return}let minX=Math.min(...cs.map(p=>p.longitude)),maxX=Math.max(...cs.map(p=>p.longitude)),minY=Math.min(...cs.map(p=>p.latitude)),maxY=Math.max(...cs.map(p=>p.latitude)),pad=90,spanX=Math.max(maxX-minX,.02),spanY=Math.max(maxY-minY,.02);points=cs.map(p=>({p,x:pad+(p.longitude-minX)/spanX*(w-2*pad),y:h-pad-(p.latitude-minY)/spanY*(h-2*pad)}));ctx.save();ctx.translate(w/2+dx, h/2+dy);ctx.scale(scale,scale);ctx.translate(-w/2,-h/2);for(let o of points){ctx.beginPath();ctx.fillStyle='#fff';ctx.arc(o.x,o.y,16,0,7);ctx.fill();ctx.beginPath();ctx.fillStyle=colors[o.p.map_state]||colors.unknown;ctx.arc(o.x,o.y,o.p.port_id===activePortId?13:10,0,7);ctx.fill();ctx.fillStyle='#173c56';ctx.font='600 13px Segoe UI';ctx.textAlign='left';ctx.fillText(o.p.name,o.x+17,o.y+4)}ctx.restore()}
const card=document.createElement('div');card.style.cssText='display:none;position:absolute;left:16px;top:14px;z-index:600;max-width:340px;max-height:72%;overflow:auto;background:#fffffff2;padding:14px;border-radius:14px;box-shadow:0 8px 24px #183b4c44';document.getElementById('map').appendChild(card);
function details(p){let bs=(p.berths||[]).map(b=>'<li><span class="state-dot" style="background:'+colors[b.state]+'"></span><button style="border:0;background:transparent;color:#175c7b;text-decoration:underline;cursor:pointer;padding:2px" onclick="berthInfo('+b.map_index+')">'+esc(b.pier)+' · '+esc(b.number)+' — '+esc(b.state_ru)+(b.boat?' · '+esc(b.boat):'')+'</button></li>').join('')||'<li>Места стоянки не созданы</li>',boats=(p.boats||[]).map(b=>esc(b.name)).join(', ')||'Нет яхт',bookings=(p.bookings||[]).map(b=>'Яхта «'+esc(b.boat_name)+'» · заявка №'+esc(b.reservation_id)).join('<br>')||'Нет оплаченных или активных заявок',photo=p.cover?'<img style="width:100%;max-height:120px;object-fit:cover;border-radius:8px" src="'+esc(p.cover)+'">':'';return '<div class="port-card">'+photo+'<h3>'+esc(p.name)+(p.is_demonstration?' <span class="demo">демонстрационный</span>':'')+(!p.is_active?' <span class="demo">неактивен</span>':'')+'</h3><b>'+esc(p.map_state_ru||'Статус не рассчитан')+'</b><p>'+esc(p.address||'Адрес не указан')+(p.city?', '+esc(p.city):'')+'<br>'+esc(p.phone||'Контакт не указан')+' · '+esc(p.opening_hours||'режим не указан')+'</p><p>'+esc(p.description||'')+'</p><b>Причалы:</b> '+(p.pier_count||0)+' · <b>Всего мест:</b> '+(p.berth_count||0)+'<br>🟢 Свободно: '+(p.free_count||0)+' · 🔴 Занято: '+(p.occupied_count||0)+'<br>🟠 Зарезервировано: '+(p.reserved_count||0)+' · ⚪ Недоступно: '+((p.unavailable_count||0)+(p.maintenance_count||0))+'<br><b>Яхты:</b> '+boats+'<br><b>Оплаченные / активные заявки:</b><br>'+bookings+'<br><b>Причалы и места:</b><ul>'+bs+'</ul><div class="berth-selected"></div></div>'}
function berthInfo(i){let b=ports.flatMap(p=>p.berths||[]).find(x=>x.map_index===i);if(!b)return;let period=b.state==='occupied'?('Период размещения: '+(b.occupied_from||'не указан')+(b.occupied_until?' — '+b.occupied_until:' — по настоящее время')):b.state==='reserved'?('Период бронирования: '+(b.reserved_from||'не указан')+(b.reserved_until?' — '+b.reserved_until:'')):'Период занятости отсутствует';let target=card.querySelector('.berth-selected');if(target)target.innerHTML='<b>Место '+esc(b.number)+' · '+esc(b.state_ru)+'</b><br>'+(b.boat?'Яхта: '+esc(b.boat)+'<br>':'')+esc(period)}
function info(p){card.innerHTML=details(p);card.style.display='block'}window.showPortDetails=id=>{const p=ports.find(x=>String(x.port_id)===String(id));if(p){activePortId=p.port_id;draw();info(p)}};function selectPort(p){activePortId=p.port_id;draw();info(p);location.href='ycm://port/'+p.port_id}const unmapped=document.getElementById('unmapped');unmapped.style.cssText='position:absolute;left:16px;top:14px;z-index:550;max-width:360px;max-height:70%;overflow:auto;background:#fffffff2;padding:12px;border-radius:12px;box-shadow:0 5px 18px #24495a33;display:none';function showUnmapped(){const rows=ports.filter(p=>p.latitude==null||p.longitude==null);if(!rows.length&&!ports.length)return;unmapped.innerHTML='<b>'+(rows.length?'Порты без заданных координат':'Порты не найдены в базе')+'</b>'+rows.map(p=>'<div><button data-port="'+p.port_id+'" style="margin-top:6px;border:0;border-radius:7px;padding:7px 10px;background:#e2f2f5;color:#17475f;cursor:pointer">'+esc(p.name)+(p.is_demonstration?' · демонстрационный':'')+'</button></div>').join('')+(rows.length?'':'<p>Проверьте, что порты и стоянки настроены в панели администратора.</p>');unmapped.style.display='block';unmapped.onclick=e=>{const id=e.target.closest('[data-port]');if(id){const p=ports.find(x=>String(x.port_id)===id.dataset.port);if(p)selectPort(p)}}}showUnmapped();cvs.addEventListener('click',e=>{let r=cvs.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,o=points.find(o=>Math.hypot(o.x-(x-r.width/2-dx)/scale-r.width/2,o.y-(y-r.height/2-dy)/scale-r.height/2)<24);if(o)selectPort(o.p)});cvs.addEventListener('mousedown',e=>drag=[e.clientX-dx,e.clientY-dy]);window.addEventListener('mouseup',()=>drag=null);window.addEventListener('mousemove',e=>{if(drag){dx=e.clientX-drag[0];dy=e.clientY-drag[1];draw()}});cvs.addEventListener('wheel',e=>{e.preventDefault();scale=Math.max(.55,Math.min(5,scale*(e.deltaY<0?1.12:.89)));draw()},{passive:false});window.addEventListener('resize',draw);new ResizeObserver(draw).observe(cvs);requestAnimationFrame(draw);if(selectedId){const p=ports.find(x=>x.port_id===selectedId);if(p)info(p)}
let s=document.createElement('script');s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';s.onload=()=>{let cs=ports.filter(p=>p.latitude!=null&&p.longitude!=null);if(!cs.length)return;document.getElementById('fallback').style.display='none';let el=document.getElementById('leaflet');el.style.display='block';document.getElementById('hint').textContent='OpenStreetMap · наведите или нажмите на маркер';leafletMap=L.map(el);let chosen=cs.find(p=>p.port_id===selectedId);if(chosen)leafletMap.setView([chosen.latitude,chosen.longitude],11);else leafletMap.fitBounds(cs.map(p=>[p.latitude,p.longitude]),{padding:[42,42],maxZoom:8});L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(leafletMap);for(const p of cs){let color=colors[p.map_state]||colors.unknown,marker=L.circleMarker([p.latitude,p.longitude],{radius:10,color:'#fff',weight:2,fillColor:color,fillOpacity:.96}).addTo(leafletMap).bindTooltip(esc(p.name)+' · '+esc(p.map_state_ru||''),{direction:'top'}).bindPopup(details(p),{maxWidth:360});marker.on('click',()=>{selectPort(p);marker.setStyle({radius:14})});if(p.port_id===selectedId)marker.openPopup()}};s.onerror=()=>document.getElementById('hint').textContent='Нет доступа к OpenStreetMap · видны локальные точки';document.head.appendChild(s);
</script></body></html>'''.replace('__PORTS__',payload).replace('__SELECTED__',json.dumps(selected_id)).replace('__STATIC_MAP__',pins_html)
        self.view.setHtml(html,QUrl.fromLocalFile(str(ROOT)+os.sep))


class AuthDialog(QDialog):
    def __init__(self,service,admin_only=False,parent=None):
        super().__init__(parent);self.service=service;self.user=None
        self.setWindowTitle("Вход сотрудника" if admin_only else "Вход или регистрация");self.resize(460,525)
        root=QVBoxLayout(self);title=QLabel("Доступ к Yacht Club Manager");title.setObjectName('Title');root.addWidget(title)
        self.tabs=QTabWidget();root.addWidget(self.tabs)
        login=QWidget();lf=QFormLayout(login);self.email=QLineEdit();self.email.setPlaceholderText('you@example.com');self.password=PasswordLineEdit()
        lf.addRow('Email',self.email);lf.addRow('Пароль',self.password);loginbtn=QPushButton('Войти');loginbtn.clicked.connect(self.login);lf.addRow(loginbtn);self.tabs.addTab(login,'Вход')
        if not admin_only:
            reg=QWidget();rf=QFormLayout(reg);self.first=QLineEdit();self.last=QLineEdit();self.phone=QLineEdit();self.regemail=QLineEdit();self.regpassword=PasswordLineEdit();self.confirm=PasswordLineEdit();self.birth=QDateEdit();self.birth.setCalendarPopup(True);self.birth.setSpecialValueText('Не указана');self.birth.setMinimumDate(QDate(1900,1,1));self.birth.setDate(QDate.currentDate())
            for label,w in [('Имя',self.first),('Фамилия',self.last),('Телефон',self.phone),('Email',self.regemail),('Пароль',self.regpassword),('Повторите пароль',self.confirm),('Дата рождения',self.birth)]:rf.addRow(label,w)
            signup=QPushButton('Создать аккаунт');signup.clicked.connect(self.register);rf.addRow(signup);self.tabs.addTab(reg,'Регистрация')
        note=QLabel('Для демонстрации: admin@yacht.local / Captain123!');note.setObjectName('Subtitle')
        if admin_only:
            self.tabs.tabBar().hide()
            root.addWidget(note)
        if admin_only:self.tabs.setCurrentIndex(0)
        self.password.returnPressed.connect(self.login)
    def login(self):
        try:
            user=self.service.authenticate(self.email.text(),self.password.text())
            if self.windowTitle()=='Вход сотрудника' and user['role_name'] not in ('admin','manager'):raise PermissionError('Для административного режима нужна учётная запись сотрудника.')
            self.user=user;self.accept()
        except Exception as e:message_error(self,'Не удалось войти',e)
    def register(self):
        try:
            birth=self.birth.date().toPython() if self.birth.date()!=QDate.currentDate() else None
            self.user=self.service.register_client(self.first.text(),self.last.text(),self.phone.text(),self.regemail.text(),self.regpassword.text(),self.confirm.text(),birth);self.accept()
        except Exception as e:message_error(self,'Проверьте данные',e)


class BoatDialog(QDialog):
    def __init__(self,service,row=None,parent=None):
        super().__init__(parent);self.service=service;self.row=row or {};self.setWindowTitle('Карточка яхты');self.resize(570,700)
        root=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);host=QWidget();form=QFormLayout(host)
        self.fields={}
        for key,label in [('name','Название'),('model','Модель')]:
            w=QLineEdit(str(self.row.get(key,'') or ''));self.fields[key]=w;form.addRow(label,w)
        for key,label,table,idcol,namecol in [('boat_type_id','Тип яхты','boat_types','boat_type_id','name'),('manufacturer_id','Производитель','manufacturers','manufacturer_id','name'),('status_id','Статус','boat_statuses','boat_status_id','name'),('current_berth_id','Место стоянки','berths','berth_id','berth_number')]:
            w=QComboBox();w.addItem('Не выбрано',None)
            rows=service.db.rows(f'SELECT {idcol},{namecol} FROM {table} ORDER BY {namecol}')
            for v,n in rows:w.addItem(str(n),v)
            old=self.row.get(key);idx=w.findData(old)
            if idx>=0:w.setCurrentIndex(idx)
            self.fields[key]=w;form.addRow(label,w)
        specs=[('production_year','Год выпуска',2010,1900,2100,0),('length','Длина, м',10,1,80,2),('width','Ширина, м',3,0.5,25,2),('draft','Осадка, м',1.5,0.2,10,2),('capacity','Вместимость',8,1,500,0),('cabin_count','Каюты',2,0,30,0),('bathroom_count','Санузлы',1,0,20,0),('engine_power','Мощность, л.с.',200,0,50000,0),('hourly_rate','Тариф за час',10000,0,10000000,2),('daily_rate','Тариф за сутки',50000,0,10000000,2),('min_hours','Минимум, часов',3,0.5,168,1),('deposit_amount','Залог',0,0,100000000,2)]
        for key,label,default,low,high,dec in specs:
            w=QDoubleSpinBox();w.setRange(low,high);w.setDecimals(dec);w.setValue(float(self.row.get(key) or default));self.fields[key]=w;form.addRow(label,w)
        for key,label in [('description','Описание'),('equipment','Оборудование')]:
            w=QTextEdit();w.setMaximumHeight(90);w.setPlainText(str(self.row.get(key,'') or ''));self.fields[key]=w;form.addRow(label,w)
        self.amenity_checks=[]
        amenity_box=QGroupBox('Удобства');amenity_layout=QVBoxLayout(amenity_box)
        selected_ids={r['amenity_id'] for r in service.db.rows('SELECT amenity_id FROM boat_amenities WHERE boat_id=%s',(self.row.get('boat_id'),))} if self.row.get('boat_id') else set()
        for item in service.db.rows('SELECT amenity_id,name FROM amenities ORDER BY name'):
            check=QCheckBox(item['name']);check.setProperty('amenity_id',item['amenity_id']);check.setChecked(item['amenity_id'] in selected_ids);self.amenity_checks.append(check);amenity_layout.addWidget(check)
        if self.amenity_checks:form.addRow(amenity_box)
        self.selected_image_paths=[]
        saved_cover=service.db.one('SELECT image_path FROM boat_images WHERE boat_id=%s ORDER BY is_cover DESC,sort_order,image_id LIMIT 1',(self.row.get('boat_id'),)) if self.row.get('boat_id') else None
        self.saved_cover_path=saved_cover.get('image_path') if saved_cover else None
        gallery_box=QGroupBox('Фотографии яхты');gallery_layout=QVBoxLayout(gallery_box)
        self.photo_preview=QLabel();self.photo_preview.setAlignment(Qt.AlignCenter);self.photo_preview.setMinimumHeight(220);self.photo_preview.setStyleSheet('background:#e9f1f3;border-radius:10px;color:#5c7587;padding:8px')
        self.photo_selection_note=QLabel('Можно выбрать несколько файлов; первый станет обложкой.');self.photo_selection_note.setObjectName('Subtitle');self.photo_selection_note.setWordWrap(True)
        photo_actions=QHBoxLayout();choose_photos=QPushButton('Выбрать с компьютера');choose_photos.setObjectName('Secondary');choose_photos.clicked.connect(self.choose_photos);clear_photos=QPushButton('Сбросить выбор');clear_photos.setObjectName('Secondary');clear_photos.clicked.connect(self.clear_photo_selection);photo_actions.addWidget(choose_photos);photo_actions.addWidget(clear_photos);photo_actions.addStretch()
        gallery_layout.addWidget(self.photo_preview);gallery_layout.addWidget(self.photo_selection_note);gallery_layout.addLayout(photo_actions);form.addRow(gallery_box)
        self.show_photo_preview()
        scroll.setWidget(host);root.addWidget(scroll);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
    def choose_photos(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Выберите фотографии яхты с компьютера','','Images (*.png *.jpg *.jpeg *.webp)')
        if paths:self.selected_image_paths=paths;self.show_photo_preview()
    def clear_photo_selection(self):self.selected_image_paths=[];self.show_photo_preview()
    def show_photo_preview(self):
        path=self.selected_image_paths[0] if self.selected_image_paths else self.saved_cover_path
        pix=QPixmap(str(Path(path) if Path(path).is_absolute() else ROOT/path)) if path else QPixmap()
        if pix.isNull():
            self.photo_preview.setPixmap(QPixmap());self.photo_preview.setText('Фотография пока не выбрана');
        else:self.photo_preview.setText('');self.photo_preview.setPixmap(pix.scaled(460,250,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        if self.selected_image_paths:self.photo_selection_note.setText(f'Выбрано файлов: {len(self.selected_image_paths)} · первый станет обложкой после сохранения.')
        elif self.saved_cover_path:self.photo_selection_note.setText('Текущая обложка. Выберите файлы с компьютера, чтобы добавить их в галерею.')
        else:self.photo_selection_note.setText('Можно выбрать несколько файлов; первый станет обложкой.')
    def values(self):
        out={}
        for key,w in self.fields.items():
            if isinstance(w,QComboBox):out[key]=w.currentData()
            elif isinstance(w,QTextEdit):out[key]=w.toPlainText().strip()
            elif isinstance(w,QDoubleSpinBox):out[key]=int(w.value()) if key in ('production_year','capacity','cabin_count','bathroom_count','engine_power') else w.value()
            else:out[key]=w.text().strip()
        if not all(out.get(k) for k in ('name','model','boat_type_id','manufacturer_id','status_id')):raise ValueError('Заполните название, модель, тип, производителя и статус.')
        out['amenity_ids']=[c.property('amenity_id') for c in self.amenity_checks if c.isChecked()]
        return out


class StaffDialog(QDialog):
    def __init__(self,service,row=None,parent=None):
        super().__init__(parent);self.service=service;row=row or {};self.setWindowTitle('Изменить сотрудника' if row else 'Создать сотрудника');self.resize(460,360);form=QFormLayout(self)
        self.first=QLineEdit(str(row.get('first_name','')));self.last=QLineEdit(str(row.get('last_name','')));self.email=QLineEdit(str(row.get('email','')));self.password=PasswordLineEdit();self.password.setPlaceholderText('Оставьте пустым, чтобы не менять')
        self.role=QComboBox();self.role.addItem('Менеджер','manager');self.role.addItem('Администратор','admin');ix=self.role.findData(row.get('role_name'));self.role.setCurrentIndex(ix if ix>=0 else 0);self.position=QComboBox()
        for x in service.db.rows('SELECT position_id,position_name FROM positions ORDER BY position_name'):self.position.addItem(x['position_name'],x['position_id'])
        ix=self.position.findData(row.get('position_id'))
        if ix>=0:self.position.setCurrentIndex(ix)
        for label,w in [('Имя',self.first),('Фамилия',self.last),('Email',self.email),('Временный пароль',self.password),('Роль',self.role),('Должность',self.position)]:form.addRow(label,w)
        hint=QLabel('Новый пароль хранится только в виде хеша.' if not row else 'Пароль можно оставить пустым без изменения.');hint.setWordWrap(True);hint.setObjectName('Subtitle');form.addRow(hint)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)


class ServiceDialog(QDialog):
    def __init__(self,row=None,parent=None):
        super().__init__(parent);row=row or {};self.setWindowTitle('Услуга');form=QFormLayout(self);self.name=QLineEdit(str(row.get('name','') or ''));self.desc=QLineEdit(str(row.get('description','') or ''));self.price=QDoubleSpinBox();self.price.setRange(0,10000000);self.price.setDecimals(2);self.price.setValue(float(row.get('price') or 0));self.unit=QLineEdit(str(row.get('pricing_unit','за заказ') or 'за заказ'));self.active=QCheckBox();self.active.setChecked(row.get('is_active',True));form.addRow('Название',self.name);form.addRow('Описание',self.desc);form.addRow('Цена, ₽',self.price);form.addRow('Единица тарифа',self.unit);form.addRow('Активна',self.active);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)
    def values(self):return {'name':self.name.text().strip(),'description':self.desc.text().strip(),'price':self.price.value(),'pricing_unit':self.unit.text().strip(),'is_active':self.active.isChecked()}


class ReservationDialog(QDialog):
    def __init__(self,service,user,boat,parent=None):
        super().__init__(parent);self.service=service;self.user=user;self.boat=boat;self.result_data=None
        self.setWindowTitle('Заявка на аренду');self.resize(540,680);root=QVBoxLayout(self)
        title=QLabel(f"Заявка · {boat['name']}");title.setObjectName('Title');root.addWidget(title)
        form=QFormLayout();self.start=QDateTimeEdit(QDateTime.currentDateTime().addDays(1));self.start.setCalendarPopup(True);self.start.setDisplayFormat('dd.MM.yyyy HH:mm')
        self.end=QDateTimeEdit(self.start.dateTime().addSecs(4*3600));self.end.setCalendarPopup(True);self.end.setDisplayFormat('dd.MM.yyyy HH:mm')
        self.passengers=QSpinBox();self.passengers.setRange(1,int(boat['capacity']));self.passengers.setValue(min(4,int(boat['capacity'])))
        form.addRow('Начало',self.start);form.addRow('Окончание',self.end);form.addRow(f"Пассажиры (макс. {boat['capacity']})",self.passengers);root.addLayout(form)
        self.svc_group=QGroupBox('Дополнительные услуги');sl=QVBoxLayout(self.svc_group);self.services=[]
        detail=service.boat_detail(boat['boat_id'])
        for s in detail['services']:
            cb=QCheckBox(f"{s['name']} · {money(s['price'])} {s['pricing_unit']}");cb.setProperty('service_id',s['service_id']);self.services.append(cb);sl.addWidget(cb)
        sc=QScrollArea();sc.setWidgetResizable(True);sc.setWidget(self.svc_group);sc.setMaximumHeight(190);root.addWidget(sc)
        self.comment=QLineEdit();self.comment.setPlaceholderText('Пожелания к маршруту или заказу')
        form2=QFormLayout();form2.addRow('Комментарий',self.comment);root.addLayout(form2)
        self.estimate=QLabel('Стоимость будет рассчитана после выбора периода');self.estimate.setObjectName('Subtitle');root.addWidget(self.estimate)
        for w in (self.start,self.end):w.dateTimeChanged.connect(self.calculate)
        self.passengers.valueChanged.connect(self.calculate)
        for w in self.services:w.stateChanged.connect(self.calculate)
        self.calculate();buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Отправить заявку');buttons.accepted.connect(self.submit);buttons.rejected.connect(self.reject);root.addWidget(buttons)
    def selections(self):return [x.property('service_id') for x in self.services if x.isChecked()]
    def calculate(self):
        try:
            client_id=self.user.get('client_id')
            if not client_id:client_id=self.service.db.value('SELECT client_id FROM clients WHERE user_id=%s',(self.user['user_id'],))
            q=self.service.quote(self.boat['boat_id'],client_id,local_dt(self.start.dateTime()),local_dt(self.end.dateTime()),self.passengers.value(),self.selections())
            self.estimate.setText(f"Яхта {money(q['base'])} · скидка {q['discount']}% · услуги {money(q['services_total'])} · Итого {money(q['total'])}")
        except Exception as e:
            if isinstance(e,ValueError):self.estimate.setText(str(e))
            else:
                logging.getLogger('yachtclub').exception('Reservation estimate failed')
                self.estimate.setText('Стоимость будет рассчитана после проверки дат и доступности.')
    def submit(self):
        try:
            client_id=self.user.get('client_id')
            if not client_id:client_id=self.service.db.value('SELECT client_id FROM clients WHERE user_id=%s',(self.user['user_id'],))
            self.result_data=self.service.create_reservation(self.user,self.boat['boat_id'],local_dt(self.start.dateTime()),local_dt(self.end.dateTime()),self.passengers.value(),self.selections(),self.comment.text())
            self.accept()
        except Exception as e:message_error(self,'Не удалось отправить заявку',e)


def make_table(rows,columns,hidden=(),parent=None):
    table=QTableWidget(len(rows),len(columns),parent);table.setAlternatingRowColors(True);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.verticalHeader().setVisible(False)
    table._column_keys=[k for k,_ in columns]
    table.setHorizontalHeaderLabels([label for key,label in columns]);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);table.horizontalHeader().setStretchLastSection(True)
    for ri,row in enumerate(rows):
        table.setRowHeight(ri,34)
        for ci,(key,label) in enumerate(columns):
            item=QTableWidgetItem(pretty(row.get(key)));item.setData(Qt.UserRole,row.get(key));table.setItem(ri,ci,item)
    for key in hidden:
        idx=next((i for i,(k,_) in enumerate(columns) if k==key),None)
        if idx is not None:table.setColumnHidden(idx,True)
    return table


def selected(table,key):
    row=table.currentRow()
    if row<0:return None
    keys=getattr(table,'_column_keys',[])
    if key not in keys:return None
    item=table.item(row,keys.index(key))
    return item.data(Qt.UserRole) if item else None


def update_table(table,rows,columns,hidden=()):
    table.setRowCount(0);table.setColumnCount(len(columns));table.setHorizontalHeaderLabels([label for _,label in columns])
    table._column_keys=[k for k,_ in columns]
    table.setAlternatingRowColors(True);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.verticalHeader().setVisible(False)
    table.setRowCount(len(rows))
    for ri,row in enumerate(rows):
        for ci,(key,label) in enumerate(columns):
            item=QTableWidgetItem(pretty(row.get(key)));item.setData(Qt.UserRole,row.get(key));table.setItem(ri,ci,item)
    for key in hidden:
        idx=next((i for i,(k,_) in enumerate(columns) if k==key),None)
        if idx is not None:table.setColumnHidden(idx,True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);table.horizontalHeader().setStretchLastSection(True)
    return table


class BoatCard(QFrame):
    details=Signal(int);favorite=Signal(int);book=Signal(int)
    def __init__(self,row,is_favorite=False,parent=None):
        super().__init__(parent);self.row=row;self.setObjectName('Card');self.setMinimumWidth(270);self.setMaximumWidth(360)
        layout=QVBoxLayout(self);layout.setContentsMargins(12,12,12,14);layout.setSpacing(8)
        name=QLabel(row['name']);name.setStyleSheet('font-size:15pt;font-weight:700;color:#153b55');name.setWordWrap(True);layout.addWidget(name)
        image=QLabel();image.setMinimumHeight(190);image.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);image.setAlignment(Qt.AlignCenter);image.setStyleSheet('background:#e9f1f3;border-radius:10px')
        path=ROOT/str(row.get('cover_image') or 'assets/boats/sailboat.svg')
        pix=QPixmap(str(path))
        if not pix.isNull():image.setPixmap(pix.scaled(420,210,Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation))
        else:image.setText('Фотография пока не добавлена')
        layout.addWidget(image)
        sub=QLabel(f"{row.get('manufacturer','')} · {row.get('model','')} · {row.get('boat_type','')}");sub.setObjectName('Subtitle');layout.addWidget(sub)
        attrs=QLabel(f"До {row['capacity']} пассажиров  ·  {row['length']} м  ·  {row['cabin_count']} кают");layout.addWidget(attrs)
        blurb=QLabel((row.get('description') or '')[:120]);blurb.setWordWrap(True);blurb.setStyleSheet('color:#5c7587');layout.addWidget(blurb)
        rate=QLabel(f"от {money(row['hourly_rate'])} / час  ·  {money(row['daily_rate'])} / сутки");rate.setStyleSheet('font-weight:700;color:#117e91');layout.addWidget(rate)
        status=QLabel('Демонстрационная иллюстрация' if 'демонстрационная' in str(row.get('cover_image','')).lower() else row.get('status_name','Свободна'));status.setObjectName('Subtitle');layout.addWidget(status)
        buttons=QHBoxLayout();d=QPushButton('Подробнее');d.setObjectName('Secondary');d.clicked.connect(lambda:self.details.emit(row['boat_id']));f=QPushButton('♥' if is_favorite else '♡');f.setObjectName('Secondary');f.setFixedWidth(44);f.clicked.connect(lambda:self.favorite.emit(row['boat_id']));b=QPushButton('Забронировать');b.clicked.connect(lambda:self.book.emit(row['boat_id']));buttons.addWidget(d);buttons.addWidget(f);buttons.addWidget(b);layout.addLayout(buttons)


class BoatDetailDialog(QDialog):
    book=Signal(int)
    def __init__(self,service,boat_id,favorite=False,parent=None):
        super().__init__(parent);self.service=service;self.data=service.boat_detail(boat_id);self.favorite=favorite;self.setWindowTitle(self.data['name']);self.resize(980,790)
        root=QVBoxLayout(self);tabs=QTabWidget();root.addWidget(tabs)
        imgs=self.data['images'];self.gallery_images=[]
        cover=next((img for img in imgs if img.get('is_cover')),imgs[0] if imgs else None)
        if cover:self.gallery_images.append((cover['image_path'],f"Яхта {self.data['name']} · обложка"))
        for image_path,caption in BOAT_INTERIOR_GALLERY.get(self.data.get('boat_type'),[]):
            if (ROOT/image_path).is_file():self.gallery_images.append((image_path,caption))
        self.gallery_images.extend((img['image_path'],img.get('caption') or f"Дополнительное фото · {self.data['name']}") for img in imgs if not img.get('is_cover'))
        if not self.gallery_images:self.gallery_images.append(('assets/boats/sailboat.svg','Иллюстрация яхты'))
        self.gallery_index=0
        overview_content=QWidget();ol=QVBoxLayout(overview_content)
        gallery_box=QGroupBox(f"Галерея · {self.data['boat_type']}");gallery_layout=QVBoxLayout(gallery_box)
        self.gallery_photo=QLabel();self.gallery_photo.setAlignment(Qt.AlignCenter);self.gallery_photo.setMinimumHeight(390);self.gallery_photo.setStyleSheet('background:#e5eff2;border-radius:12px;padding:8px;color:#5c7587')
        navigation=QHBoxLayout();previous=QPushButton('‹');previous.setAccessibleName('Предыдущее фото');previous.setToolTip('Предыдущее фото');previous.setObjectName('Secondary');previous.setFixedSize(48,44);previous.clicked.connect(lambda:self.show_gallery_image(self.gallery_index-1));navigation.addWidget(previous)
        navigation.addWidget(self.gallery_photo,1)
        following=QPushButton('›');following.setAccessibleName('Следующее фото');following.setToolTip('Следующее фото');following.setObjectName('Secondary');following.setFixedSize(48,44);following.clicked.connect(lambda:self.show_gallery_image(self.gallery_index+1));navigation.addWidget(following)
        self.gallery_caption=QLabel();self.gallery_caption.setAlignment(Qt.AlignCenter);self.gallery_caption.setObjectName('Subtitle');gallery_layout.addLayout(navigation);gallery_layout.addWidget(self.gallery_caption);ol.addWidget(gallery_box)
        self.show_gallery_image(0)
        ol.addWidget(QLabel(self.data['description']));ol.addWidget(QLabel(f"{self.data['boat_type']} · {self.data['manufacturer']} · {self.data['model']} · {self.data['production_year']}"));ol.addWidget(QLabel(f"Длина {self.data['length']} м · ширина {self.data['width']} м · осадка {self.data['draft']} м · пассажиров {self.data['capacity']} · кают {self.data['cabin_count']} · санузлов {self.data['bathroom_count']}"));ol.addWidget(QLabel(f"Двигатель {self.data['engine_power']} л.с. · минимальная аренда {self.data['min_hours']} ч · залог {money(self.data['deposit_amount'])}"));ol.addWidget(QLabel('Оборудование: '+str(self.data['equipment'])));ol.addWidget(QLabel('Удобства: '+', '.join(x['name'] for x in self.data['amenities'])))
        overview_scroll=QScrollArea();overview_scroll.setWidgetResizable(True);overview_scroll.setWidget(overview_content);tabs.addTab(overview_scroll,'О яхте')
        svc=QWidget();svl=QVBoxLayout(svc)
        for s in self.data['services']:svl.addWidget(QLabel(f"{s['name']} · {money(s['price'])} {s['pricing_unit']} — {s['description']}"))
        tabs.addTab(svc,'Услуги')
        b=QPushButton('Выбрать даты и подать заявку');b.clicked.connect(lambda:self.book.emit(boat_id));root.addWidget(b)
        QTimer.singleShot(0,lambda:self.show_gallery_image(self.gallery_index))
    def show_gallery_image(self,index):
        if not self.gallery_images:return
        self.gallery_index=index%len(self.gallery_images)
        image_path=Path(str(self.gallery_images[self.gallery_index][0]));image_path=image_path if image_path.is_absolute() else ROOT/image_path
        pix=QPixmap(str(image_path));self.gallery_photo.setText('')
        if pix.isNull():self.gallery_photo.setText('Не удалось открыть файл изображения');self.gallery_photo.setPixmap(QPixmap())
        else:
            width=max(320,self.gallery_photo.width()-20);height=max(300,self.gallery_photo.height()-20)
            self.gallery_photo.setPixmap(pix.scaled(width,height,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        self.gallery_caption.setText(f'{self.gallery_images[self.gallery_index][1]} · {self.gallery_index+1} / {len(self.gallery_images)}')
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'gallery_index'):self.show_gallery_image(self.gallery_index)


class MetricCard(QFrame):
    def __init__(self,title,value,detail='',parent=None):
        super().__init__(parent);self.setObjectName('MetricCard');l=QVBoxLayout(self);t=QLabel(title);t.setObjectName('MetricCaption');v=QLabel(str(value));v.setObjectName('Metric');l.addWidget(t);l.addWidget(v)
        if detail:
            label=QLabel(detail);label.setObjectName('Subtitle');l.addWidget(label)


class ChartCanvas(FigureCanvasQTAgg):
    def __init__(self,parent=None):self.figure=Figure(figsize=(8,4),tight_layout=True);super().__init__(self.figure);self.setParent(parent)
    def wheelEvent(self,event):
        parent=self.parentWidget()
        while parent is not None and not isinstance(parent,QScrollArea):parent=parent.parentWidget()
        if parent is not None:parent.wheelEvent(event)
        else:super().wheelEvent(event)


class MainWindow(QMainWindow):
    def __init__(self,db,settings):
        super().__init__();self.db=db;self.settings=settings;self.service=YachtService(db);self.user=None;self.pending_booking=None;self.cards=[]
        self.setWindowTitle('Yacht Club Manager');self.resize(1500,960);self.setMinimumSize(760,600)
        root=QVBoxLayout();host=QWidget();host.setLayout(root);self.setCentralWidget(host)
        top=QFrame();self.client_topbar=top;top.setObjectName('Topbar');top.setFixedHeight(72);tl=QHBoxLayout(top);tl.setContentsMargins(26,8,26,8)
        brand=QLabel('⚓ YACHT CLUB');brand.setObjectName('Brand');tl.addWidget(brand)
        self.client_nav={}
        for text,page in [('Главная','home'),('Каталог','catalog'),('Порты','portmap'),('Услуги','services'),('Погода','weather'),('О клубе','about'),('Избранное','favorites')]:
            btn=QPushButton(text);btn.setObjectName('ClientNav');btn.setProperty('clientNav',True);btn.clicked.connect(lambda _,p=page:self.go(p));self.client_nav[page]=btn;tl.addWidget(btn)
        tl.addStretch();self.account_btn=QPushButton('Войти');self.account_btn.clicked.connect(self.account_action);tl.addWidget(self.account_btn)
        self.admin_btn=QPushButton('Вход для администратора');self.admin_btn.setObjectName('Secondary');self.admin_btn.clicked.connect(self.admin_login);tl.addWidget(self.admin_btn)
        root.addWidget(top);self.stack=QStackedWidget();root.addWidget(self.stack,1);self.pages={}
        for name,builder in [('home',self.build_home),('catalog',self.build_catalog),('portmap',self.build_port_map),('services',self.build_services),('weather',self.build_weather),('about',self.build_about),('favorites',self.build_favorites),('cabinet',self.build_cabinet),('admin',self.build_admin)]:
            content=builder();self.pages[name]=content if name=='admin' else self.scroll_page(content);self.stack.addWidget(self.pages[name])
        self.go('home');self.refresh_home();self.refresh_weather_card()

    @staticmethod
    def scroll_page(content):
        area=QScrollArea();area.setWidgetResizable(True);area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded);area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);area.setWidget(content);return area

    def section(self,title,subtitle=''):
        box=QVBoxLayout();t=QLabel(title);t.setObjectName('Title');box.addWidget(t)
        if subtitle:s=QLabel(subtitle);s.setObjectName('Subtitle');box.addWidget(s)
        return box

    def go(self,page):
        if page in ('favorites','cabinet') and not (self.user and self.user['role_name']=='client'):
            self.login()
            if not (self.user and self.user['role_name']=='client'):return
        if page=='admin' and not (self.user and self.user['role_name'] in ('admin','manager')):
            self.admin_login()
            if not (self.user and self.user['role_name'] in ('admin','manager')):return
        self.stack.setCurrentWidget(self.pages[page])
        is_admin=page=='admin'
        self.client_topbar.setVisible(not is_admin)
        for key,button in self.client_nav.items():
            button.setProperty('active',key==page);button.style().unpolish(button);button.style().polish(button)
        if page=='catalog':self.refresh_catalog()
        elif page=='favorites':self.refresh_favorites()
        elif page=='cabinet':self.refresh_cabinet()
        elif page=='services':self.refresh_services()
        elif page=='portmap':self.refresh_client_port_map()
        elif page=='weather':self.refresh_weather_page()
        elif page=='admin':self.refresh_admin()
        self.update_account_button()

    def update_account_button(self):
        if self.user:
            name=self.user.get('first_name') or self.user.get('email','Аккаунт').split('@')[0]
            self.account_btn.setText(f"{name} · Выйти")
        else:self.account_btn.setText('Войти')
        self.admin_btn.setVisible(not bool(self.user and self.user.get('role_name') in ('admin','manager')))

    def exit_admin(self):
        self.user=None;self.pending_booking=None
        self.go('home');self.update_account_button()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        for name in ('home_cards','catalog_grid','services_grid','favorite_grid'):
            grid=getattr(self,name,None)
            if not grid:continue
            host=grid.parentWidget()
            width=host.width() if host else self.width()
            columns=max(1,min(5,(width+20)//310))
            widgets=[grid.itemAt(i).widget() for i in range(grid.count()) if grid.itemAt(i).widget()]
            for i,widget in enumerate(widgets):grid.addWidget(widget,i//columns,i%columns)

    def account_action(self):
        if self.user:
            answer=QMessageBox.question(self,'Выйти из аккаунта?','Текущая сессия будет завершена.')
            if answer==QMessageBox.Yes:self.user=None;self.go('home')
        else:self.login()

    def login(self):
        dlg=AuthDialog(self.service,parent=self)
        if dlg.exec()==QDialog.Accepted:
            self.set_user(dlg.user)

    def admin_login(self):
        dlg=AuthDialog(self.service,admin_only=True,parent=self)
        if dlg.exec()==QDialog.Accepted:self.set_user(dlg.user)

    def set_user(self,user):
        self.user=user;self.update_account_button()
        if user['role_name'] in ('admin','manager'):self.go('admin')
        elif self.pending_booking:
            boat_id=self.pending_booking;self.pending_booking=None;self.open_booking(boat_id)
        else:self.go('cabinet')

    def need_login(self,action):
        if self.user and self.user.get('role_name')=='client':return True
        self.pending_booking=action if isinstance(action,int) else None
        self.login()
        if self.user and self.user.get('role_name')=='client':return True
        return False

    def build_home(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(28,24,28,26);root.setSpacing(20)
        hero=HeroBanner(ROOT/'assets'/'hero-yacht.png')
        hl=QVBoxLayout(hero);hl.setContentsMargins(42,36,42,36);hl.addStretch();h=QLabel('Ваш маршрут начинается здесь');h.setObjectName('HeroTitle');hl.addWidget(h);s=QLabel('Море ближе, чем кажется. Выберите яхту для особенного дня.');s.setObjectName('HeroSub');hl.addWidget(s);b=QPushButton('Выбрать яхту');b.setFixedWidth(190);b.clicked.connect(lambda:self.go('catalog'));hl.addWidget(b);hl.addStretch();root.addWidget(hero)
        benefits=QHBoxLayout()
        for title,desc in [('Флот с заботой','Проверенные яхты и регулярные осмотры'),('Безопасный выход','Погода и правила клуба учитываются в заявке'),('Сервис на борту','Капитан, питание, оборудование и трансфер'),('Понятный процесс','Заявка, подтверждение, оплата и квитанция')]:
            f=QFrame();f.setObjectName('Card');v=QVBoxLayout(f);t=QLabel(title);t.setStyleSheet('font-size:12pt;font-weight:700');v.addWidget(t);v.addWidget(QLabel(desc));benefits.addWidget(f)
        root.addLayout(benefits);title=QLabel('Популярные яхты');title.setObjectName('Title');root.addWidget(title);self.home_cards=QGridLayout();root.addLayout(self.home_cards)
        weather=QFrame();weather.setObjectName('Card');wl=QHBoxLayout(weather);self.home_weather=QLabel('Погода загружается…');wl.addWidget(QLabel('☀'));wl.addWidget(self.home_weather);wb=QPushButton('Подробный прогноз');wb.setObjectName('Secondary');wb.clicked.connect(lambda:self.go('weather'));wl.addStretch();wl.addWidget(wb);root.addWidget(weather)
        flow=QLabel('Выберите яхту   →   Отправьте заявку   →   Получите подтверждение   →   Оплатите   →   Отправляйтесь в море');flow.setAlignment(Qt.AlignCenter);flow.setStyleSheet('font-size:11pt;font-weight:650;color:#147f91;padding:14px');root.addWidget(flow);root.addStretch()
        return page

    def build_catalog(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(28,24,28,22);root.addLayout(self.section('Каталог яхт','Подберите судно по датам, вместимости и формату отдыха.'))
        filters=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Название, модель или производитель');filters.addWidget(self.search,3)
        self.type_filter=QComboBox();self.type_filter.addItem('Все типы');self.type_filter.addItems([r['name'] for r in self.db.rows('SELECT name FROM boat_types ORDER BY name')]);filters.addWidget(self.type_filter)
        self.catalog_port_filter=QComboBox();self.catalog_port_filter.addItem('Все порты',None)
        try:
            for p in self.service.map_ports():self.catalog_port_filter.addItem(p['name'],p['port_id'])
        except Exception:pass
        filters.addWidget(self.catalog_port_filter)
        self.manufacturer_filter=QComboBox();self.manufacturer_filter.addItem('Все производители');self.manufacturer_filter.addItems([r['name'] for r in self.db.rows('SELECT name FROM manufacturers ORDER BY name')]);filters.addWidget(self.manufacturer_filter)
        self.capacity_filter=QSpinBox();self.capacity_filter.setRange(0,200);self.capacity_filter.setPrefix('Пассажиров ≥ ');filters.addWidget(self.capacity_filter)
        self.cabin_filter=QSpinBox();self.cabin_filter.setRange(0,30);self.cabin_filter.setPrefix('Кают ≥ ');filters.addWidget(self.cabin_filter)
        self.price_filter=QDoubleSpinBox();self.price_filter.setRange(0,10000000);self.price_filter.setDecimals(0);self.price_filter.setSingleStep(5000);self.price_filter.setPrefix('Макс. ₽/сутки ');filters.addWidget(self.price_filter)
        self.sort_filter=QComboBox();self.sort_filter.addItems(['Рекомендуемые','Популярные','Дешевле','Дороже','По названию','Вместимость']);filters.addWidget(self.sort_filter)
        searchbtn=QPushButton('Найти');searchbtn.clicked.connect(self.refresh_catalog);reset=QPushButton('Сбросить');reset.setObjectName('Secondary');reset.clicked.connect(self.reset_catalog);filters.addWidget(searchbtn);filters.addWidget(reset);root.addLayout(filters)
        dates=QHBoxLayout();self.date_filter=QCheckBox('Показать доступные на даты');dates.addWidget(self.date_filter);self.filter_start=QDateTimeEdit(QDateTime.currentDateTime().addDays(1));self.filter_start.setCalendarPopup(True);self.filter_start.setDisplayFormat('dd.MM.yyyy HH:mm');self.filter_end=QDateTimeEdit(self.filter_start.dateTime().addSecs(4*3600));self.filter_end.setCalendarPopup(True);self.filter_end.setDisplayFormat('dd.MM.yyyy HH:mm');self.filter_passengers=QSpinBox();self.filter_passengers.setRange(1,200);self.filter_passengers.setPrefix('Пассажиры ');dates.addWidget(self.filter_start);dates.addWidget(self.filter_end);dates.addWidget(self.filter_passengers);dates.addStretch();root.addLayout(dates)
        self.catalog_count=QLabel();self.catalog_count.setObjectName('Subtitle');root.addWidget(self.catalog_count)
        scroll=QScrollArea();scroll.setWidgetResizable(True);self.catalog_host=QWidget();self.catalog_grid=QGridLayout(self.catalog_host);self.catalog_grid.setSpacing(16);scroll.setWidget(self.catalog_host);root.addWidget(scroll,1)
        for w in (self.search,self.type_filter,self.catalog_port_filter,self.manufacturer_filter,self.capacity_filter,self.cabin_filter,self.price_filter,self.sort_filter,self.date_filter,self.filter_start,self.filter_end,self.filter_passengers):
            if hasattr(w,'textChanged'):w.textChanged.connect(self.refresh_catalog)
            elif hasattr(w,'valueChanged'):w.valueChanged.connect(self.refresh_catalog)
            elif hasattr(w,'dateTimeChanged'):w.dateTimeChanged.connect(self.refresh_catalog)
        self.type_filter.currentIndexChanged.connect(self.refresh_catalog);self.catalog_port_filter.currentIndexChanged.connect(self.refresh_catalog);self.manufacturer_filter.currentIndexChanged.connect(self.refresh_catalog);self.sort_filter.currentIndexChanged.connect(self.refresh_catalog);self.date_filter.stateChanged.connect(self.refresh_catalog)
        return page

    def reset_catalog(self):
        self.search.clear();self.type_filter.setCurrentIndex(0);self.catalog_port_filter.setCurrentIndex(0);self.manufacturer_filter.setCurrentIndex(0);self.capacity_filter.setValue(0);self.cabin_filter.setValue(0);self.price_filter.setValue(0);self.date_filter.setChecked(False);self.refresh_catalog()

    def clear_grid(self,grid):
        while grid.count():
            item=grid.takeAt(0);w=item.widget()
            if w:w.deleteLater()

    def refresh_catalog(self):
        if not hasattr(self,'catalog_grid'):return
        try:
            selected_port=self.catalog_port_filter.currentData();self.catalog_port_filter.blockSignals(True);self.catalog_port_filter.clear();self.catalog_port_filter.addItem('Все порты',None)
            for p in self.service.map_ports():self.catalog_port_filter.addItem(p['name'],p['port_id'])
            ix=self.catalog_port_filter.findData(selected_port)
            if ix>=0:self.catalog_port_filter.setCurrentIndex(ix)
            self.catalog_port_filter.blockSignals(False)
            bt=self.type_filter.currentText();mf=self.manufacturer_filter.currentText();start=end=None
            if self.date_filter.isChecked():start=local_dt(self.filter_start.dateTime());end=local_dt(self.filter_end.dateTime())
            rows=self.service.catalog(self.search.text(),None if bt=='Все типы' else bt,None if mf=='Все производители' else mf,self.capacity_filter.value(),self.cabin_filter.value(),max_price=self.price_filter.value() or None,sort=self.sort_filter.currentText(),start_at=start,end_at=end,passengers=self.filter_passengers.value(),port_id=self.catalog_port_filter.currentData())
            self.clear_grid(self.catalog_grid)
            favorites=set()
            if self.user and self.user.get('role_name')=='client':favorites={r['boat_id'] for r in self.service.favorites(self.user)}
            if not rows:
                empty=QFrame();empty.setObjectName('Card');v=QVBoxLayout(empty);v.addWidget(QLabel('Подходящих яхт пока нет'));again=QPushButton('Сбросить фильтры');again.clicked.connect(self.reset_catalog);v.addWidget(again);self.catalog_grid.addWidget(empty,0,0)
            else:
                for i,row in enumerate(rows):
                    card=BoatCard(row,row['boat_id'] in favorites);card.details.connect(self.show_boat_detail);card.favorite.connect(self.favorite_action);card.book.connect(self.open_booking);self.catalog_grid.addWidget(card,i//max(1,min(5,(self.catalog_host.width()+20)//310)),i%max(1,min(5,(self.catalog_host.width()+20)//310)))
            self.catalog_count.setText(f"Найдено яхт: {len(rows)}")
        except Exception as e:message_error(self,'Не удалось загрузить каталог',e)

    def show_boat_detail(self,boat_id):
        try:
            isfav=False
            if self.user and self.user.get('role_name')=='client':isfav=any(x['boat_id']==boat_id for x in self.service.favorites(self.user))
            dlg=BoatDetailDialog(self.service,boat_id,isfav,self);dlg.book.connect(lambda bid:(dlg.accept(),self.open_booking(bid)));dlg.exec()
        except Exception as e:message_error(self,'Не удалось открыть карточку яхты',e)

    def favorite_action(self,boat_id):
        if not self.need_login(None):return
        try:added=self.service.toggle_favorite(self.user,boat_id);QMessageBox.information(self,'Избранное','Яхта добавлена в избранное.' if added else 'Яхта удалена из избранного.');self.refresh_catalog()
        except Exception as e:message_error(self,'Не удалось изменить избранное',e)

    def build_port_map(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(28,24,28,22);root.addLayout(self.section('Карта портов','Порты, места стоянки и доступные яхты из базы клуба.'))
        self.client_portmap=PortMapWidget();self.client_portmap.setMinimumHeight(560);self.client_portmap.catalogRequested.connect(self.open_catalog_from_port);self.client_portmap.portSelected.connect(self.client_portmap.show_port_details);root.addWidget(self.client_portmap,1);return page

    def refresh_client_port_map(self):
        try:self.client_portmap.set_ports(self.service.map_ports())
        except Exception as e:message_error(self,'Карта портов недоступна',e)

    def open_catalog_from_port(self,port_id):
        if hasattr(self,'catalog_port_filter'):
            idx=self.catalog_port_filter.findData(port_id)
            if idx>=0:self.catalog_port_filter.setCurrentIndex(idx)
        self.go('catalog')

    def open_port_map(self,port_id=None):
        dlg=QDialog(self);dlg.setWindowTitle('Карта портов');dlg.resize(1050,720);layout=QVBoxLayout(dlg);view=PortMapWidget(dlg);view.catalogRequested.connect(lambda pid:(dlg.accept(),self.open_catalog_from_port(pid)));view.portSelected.connect(view.show_port_details);layout.addWidget(view)
        try:view.set_ports(self.service.map_ports(selected_id=port_id),port_id);dlg.exec()
        except Exception as e:message_error(self,'Карта портов недоступна',e)

    def open_booking(self,boat_id):
        if not(self.user and self.user.get('role_name')=='client'):
            self.pending_booking=None
            dlg=AuthDialog(self.service,parent=self)
            if dlg.exec()!=QDialog.Accepted:return
            if dlg.user['role_name']!='client':QMessageBox.warning(self,'Клиентский вход','Для подачи заявки войдите как клиент.');return
            self.user=dlg.user;self.update_account_button()
        try:
            boat=self.service.boat_detail(boat_id);dlg=ReservationDialog(self.service,self.user,boat,self)
            if dlg.exec()==QDialog.Accepted:
                QMessageBox.information(self,'Заявка отправлена',f"Заявка №{dlg.result_data['reservation_id']} отправлена администратору. Статус: ожидает подтверждения.");self.go('cabinet')
        except Exception as e:message_error(self,'Не удалось оформить заявку',e)

    def build_services(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(28,24,28,22);root.addLayout(self.section('Сервис на борту','Дополнительные услуги сохраняются по цене на момент подачи заявки.'));self.services_grid=QGridLayout();root.addLayout(self.services_grid);root.addStretch();return page

    def refresh_services(self):
        self.clear_grid(self.services_grid);rows=self.db.rows('SELECT * FROM services WHERE is_active ORDER BY name')
        for i,r in enumerate(rows):
            f=QFrame();f.setObjectName('Card');v=QVBoxLayout(f);t=QLabel(r['name']);t.setStyleSheet('font-size:14pt;font-weight:700');v.addWidget(t);v.addWidget(QLabel(r['description']));v.addWidget(QLabel(f"{money(r['price'])} {r['pricing_unit']}"));self.services_grid.addWidget(f,i//3,i%3)

    def build_about(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(34,32,34,30);root.setSpacing(18);root.addLayout(self.section('О яхт-клубе','Отдых, безопасность и морские маршруты в одном сервисе.'))
        intro=QFrame();intro.setObjectName('Card');il=QVBoxLayout(intro);il.setContentsMargins(28,24,28,24);il.setSpacing(10)
        for heading,body in [
            ('Море ближе, чем кажется','Yacht Club Manager — настольная система для знакомства с флотом и организации аренды яхт. В открытом каталоге можно искать суда, сравнивать характеристики и тарифы, изучать оснащение и выбирать даты выхода.'),
            ('Как проходит бронирование','После входа клиент выбирает судно, время аренды, число пассажиров и дополнительные услуги. Приложение рассчитывает предварительную стоимость и проверяет вместимость, расписание заявок и периоды обслуживания. Новая заявка отправляется менеджеру клуба на подтверждение.'),
            ('Поддержка на каждом этапе','В личном кабинете доступны заявки, сведения об оплате, уведомления и учебные квитанции. Сотрудники клуба управляют флотом, стоянками, обслуживанием, услугами и платежами в отдельном административном рабочем пространстве.'),
            ('Безопасность и погодные данные','Погодная информация в приложении справочная. Она не заменяет официальные навигационные предупреждения, прогнозы профильных служб и решение капитана. Фактические условия выхода следует уточнять перед поездкой.'),
            ('Демонстрационные материалы','В учебной базе могут использоваться демонстрационные записи и иллюстрации. Они не являются подтверждением наличия конкретного судна в реальном клубе. Учебные платежи не проводят банковскую операцию, а квитанции приложения не являются фискальными чеками.')
        ]:
            title=QLabel(heading);title.setObjectName('AboutHeading');il.addWidget(title)
            text=QLabel(body);text.setObjectName('AboutBody');text.setWordWrap(True);text.setMinimumWidth(0);il.addWidget(text)
        root.addWidget(intro);root.addStretch();return page

    def build_favorites(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(28,24,28,22);root.addLayout(self.section('Избранное','Сохранённые яхты для быстрого сравнения.'));self.favorite_grid=QGridLayout();root.addLayout(self.favorite_grid);root.addStretch();return page

    def refresh_favorites(self):
        self.clear_grid(self.favorite_grid)
        try:
            rows=self.service.favorites(self.user)
            for i,row in enumerate(rows):
                card=BoatCard(row,True);card.details.connect(self.show_boat_detail);card.favorite.connect(self.favorite_action);card.book.connect(self.open_booking);self.favorite_grid.addWidget(card,i//3,i%3)
            if not rows:self.favorite_grid.addWidget(QLabel('В избранном пока пусто. Добавьте яхты из каталога.'))
        except Exception as e:message_error(self,'Не удалось загрузить избранное',e)

    def refresh_home(self):
        if not hasattr(self,'home_cards'):return
        self.clear_grid(self.home_cards)
        try:
            rows=self.service.catalog(sort='Популярные')[:4]
            for i,row in enumerate(rows):
                card=BoatCard(row);card.details.connect(self.show_boat_detail);card.favorite.connect(self.favorite_action);card.book.connect(self.open_booking);self.home_cards.addWidget(card,0,i)
        except Exception:
            logging.getLogger('yachtclub').exception('Popular boats could not be loaded')
            empty=QLabel('Популярные яхты временно недоступны. Попробуйте обновить страницу.');self.home_cards.addWidget(empty,0,0)

    def build_cabinet(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(28,24,28,22);root.addLayout(self.section('Личный кабинет','Ваши заявки, оплаты, уведомления и членство.'))
        self.cabinet_tabs=QTabWidget();root.addWidget(self.cabinet_tabs,1)
        profile=QWidget();pl=QVBoxLayout(profile);self.profile_card=QFrame();self.profile_card.setObjectName('Card');self.profile_layout=QFormLayout(self.profile_card);pl.addWidget(self.profile_card);prof_btn=QPushButton('Изменить контакты');prof_btn.clicked.connect(self.edit_profile);pl.addWidget(prof_btn,alignment=Qt.AlignLeft);pwd=QPushButton('Сменить пароль');pwd.setObjectName('Secondary');pwd.clicked.connect(self.change_password_dialog);pl.addWidget(pwd,alignment=Qt.AlignLeft);pl.addStretch();self.cabinet_tabs.addTab(profile,'Профиль')
        orders=QWidget();ol=QVBoxLayout(orders);self.orders_table=QTableWidget();ol.addWidget(self.orders_table,1);obar=QHBoxLayout()
        for title,handler in [('Открыть детали',self.show_order_details),('Демо-оплата',self.pay_order),('Перевод',self.transfer_order),('Отменить заявку',self.cancel_order),('Сохранить квитанцию',self.save_receipt)]:
            b=QPushButton(title);b.setObjectName('Secondary' if title!='Демо-оплата' else '');b.clicked.connect(handler);obar.addWidget(b)
        ol.addLayout(obar);self.cabinet_tabs.addTab(orders,'Заявки и бронирования')
        paypage=QWidget();payl=QVBoxLayout(paypage);self.client_payments_table=QTableWidget();payl.addWidget(self.client_payments_table,1);self.cabinet_tabs.addTab(paypage,'Платежи')
        notif=QWidget();nl=QVBoxLayout(notif);self.client_notifications=QListWidget();nl.addWidget(self.client_notifications);notify_actions=QHBoxLayout();place_btn=QPushButton('Место отправления на карте');place_btn.setObjectName('Secondary');place_btn.clicked.connect(self.open_notification_map);notify_actions.addWidget(place_btn);notify_actions.addStretch();nb=QPushButton('Отметить всё прочитанным');nb.clicked.connect(lambda:self.mark_all_notifications());notify_actions.addWidget(nb);nl.addLayout(notify_actions);self.cabinet_tabs.addTab(notif,'Уведомления')
        return page

    def refresh_cabinet(self):
        if not(self.user and self.user.get('role_name')=='client'):return
        try:
            profile=self.service.user_client_profile(self.user)
            while self.profile_layout.rowCount():self.profile_layout.removeRow(0)
            for label,value in [('Имя',profile['first_name']),('Фамилия',profile['last_name']),('Email',profile['email']),('Телефон',profile['phone']),('Дата регистрации',pretty(profile['registered_at'])),('Членство',profile.get('membership') or 'Нет активного членства'),('Срок членства',pretty(profile.get('membership_end'))),('Скидка',f"{profile.get('discount_percent') or 0}%")]:
                self.profile_layout.addRow(label,QLabel(str(value)))
            rows=self.service.user_reservations(self.user);cols=[('reservation_id','№'),('boat_name','Яхта'),('port_name','Порт отправления'),('start_at','Начало'),('end_at','Окончание'),('passenger_count','Пассажиры'),('status_title','Статус'),('charged','Начислено'),('paid','Оплачено'),('balance','Остаток')]
            self.orders_table=update_table(self.orders_table,rows,cols,hidden=('reservation_id',))
            pays=self.service.user_payments(self.user);self.client_payments_table=update_table(self.client_payments_table,pays,[('payment_id','Платёж'),('reservation_id','Заявка'),('boat_name','Яхта'),('amount','Сумма'),('status','Статус'),('method_id','Способ ID'),('created_at','Создан'),('receipt_number','Квитанция')],hidden=('payment_id',))
            self.client_notifications.clear()
            for n in self.service.notifications(self.user):
                item=QListWidgetItem(('● ' if not n['is_read'] else '○ ')+n['title']+' · '+n['message']);item.setData(Qt.UserRole,n['notification_id']);item.setData(Qt.UserRole+1,n.get('related_entity'));item.setData(Qt.UserRole+2,n.get('related_id'));self.client_notifications.addItem(item)
        except Exception as e:message_error(self,'Не удалось загрузить кабинет',e)

    def selected_order(self):
        return selected(self.orders_table,'reservation_id')

    def show_order_details(self):
        rid=self.selected_order()
        if not rid:return
        row=next((r for r in self.service.user_reservations(self.user) if r['reservation_id']==rid),None)
        if not row:return
        dlg=QDialog(self);dlg.setWindowTitle(f"Заявка №{rid}");dlg.resize(520,460);v=QVBoxLayout(dlg)
        for label,key in [('Яхта','boat_name'),('Период','start_at'),('Пассажиры','passenger_count'),('Состояние','status_title'),('Стоимость','charged'),('Оплачено','paid'),('Остаток','balance'),('Услуги','services'),('Комментарий','customer_comment')]:
            v.addWidget(QLabel(f"{label}: {pretty(row.get(key))}"))
        if row.get('port_name'):
            place=QGroupBox('Место отправления');pl=QVBoxLayout(place)
            if row.get('port_image'):
                pix=QPixmap(str(ROOT/row['port_image']))
                if not pix.isNull():photo=QLabel();photo.setPixmap(pix.scaled(430,150,Qt.KeepAspectRatio,Qt.SmoothTransformation));pl.addWidget(photo)
            pl.addWidget(QLabel(f"Порт: {row['port_name']}"));pl.addWidget(QLabel(f"Адрес: {row.get('port_address') or 'не указан'}{', '+row.get('port_city','') if row.get('port_city') else ''}"))
            if row.get('pickup_pier_name'):pl.addWidget(QLabel(f"Причал: {row['pickup_pier_name']} · место: {row.get('pickup_berth_number') or 'уточняется'}"))
            else:pl.addWidget(QLabel('Точное место стоянки будет уточнено дополнительно.'))
            pl.addWidget(QLabel(f"Прибытие: {pretty(row.get('arrival_at') or row.get('start_at'))} · Контакт: {row.get('port_phone') or 'не указан'}"))
            map_btn=QPushButton('Посмотреть на карте');map_btn.clicked.connect(lambda _,pid=(row.get('port_id') or row.get('resolved_port_id')):self.open_port_map(pid));pl.addWidget(map_btn,alignment=Qt.AlignLeft);v.addWidget(place)
        history=self.db.rows("SELECT old_status_code,new_status_code,changed_at,note FROM reservation_status_history WHERE reservation_id=%s ORDER BY changed_at",(rid,))
        box=QGroupBox('История изменений');bl=QVBoxLayout(box)
        for h in history:bl.addWidget(QLabel(f"{pretty(h['changed_at'])}: {h['old_status_code'] or '—'} → {h['new_status_code']} · {h['note']}"))
        v.addWidget(box)
        dlg.exec()

    def open_notification_map(self):
        item=self.client_notifications.currentItem() if hasattr(self,'client_notifications') else None
        if not item:QMessageBox.information(self,'Выберите уведомление','Выберите уведомление о бронировании.');return
        if item.data(Qt.UserRole+1)!='reservation':QMessageBox.information(self,'Место отправления','В выбранном уведомлении нет места отправления.');return
        rid=item.data(Qt.UserRole+2);row=next((r for r in self.service.user_reservations(self.user) if r['reservation_id']==rid),None)
        if not row or not (row.get('port_id') or row.get('resolved_port_id')):QMessageBox.information(self,'Место отправления','Порт для этой заявки ещё не назначен.');return
        self.open_port_map(row.get('port_id') or row.get('resolved_port_id'))

    def pay_order(self):
        rid=self.selected_order()
        if not rid:QMessageBox.information(self,'Выберите заявку','Выберите запись в таблице.');return
        ans=QMessageBox.question(self,'Демо-оплата','Имитировать успешную оплату?\nЭто учебная операция: реальные платёжные данные не используются.',QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel)
        if ans==QMessageBox.Cancel:return
        try:
            p=self.service.demo_payment(self.user,rid,ans==QMessageBox.Yes)
            if p['status']=='confirmed':QMessageBox.information(self,'Оплата подтверждена',f"Учебная оплата {money(p['amount'])} прошла. Квитанция доступна в заказе.\n\n{p.get('pickup_message','Место отправления указано в карточке бронирования.')}")
            else:QMessageBox.warning(self,'Оплата не прошла','Учебный платёж отклонён; повторите оплату позже.')
            self.refresh_cabinet()
        except Exception as e:message_error(self,'Оплата недоступна',e)

    def transfer_order(self):
        rid=self.selected_order()
        if not rid:QMessageBox.information(self,'Выберите заявку','Выберите запись в таблице.');return
        ref,ok=QInputDialog.getText(self,'Перевод по реквизитам','Номер операции или назначение (не вводите платёжные секреты):')
        if not ok:return
        try:self.service.request_transfer_payment(self.user,rid,ref);QMessageBox.information(self,'Платёж создан','Перевод ожидает проверки администратором.');self.refresh_cabinet()
        except Exception as e:message_error(self,'Не удалось зарегистрировать перевод',e)

    def cancel_order(self):
        rid=self.selected_order()
        if not rid:return
        if QMessageBox.question(self,'Отменить заявку?',f"Отменить заявку №{rid}?")==QMessageBox.Yes:
            try:self.service.cancel_reservation(self.user,rid);self.refresh_cabinet()
            except Exception as e:message_error(self,'Не удалось отменить заявку',e)

    def save_receipt(self):
        rid=self.selected_order()
        if not rid:return
        try:
            rows=self.service.receipts(self.user,rid)
            if not rows:raise ValueError('Подтверждённая квитанция пока не сформирована.')
            data=rows[0];default=str(ROOT/'receipts'/f"{data['receipt_number']}.pdf")
            path,_=QFileDialog.getSaveFileName(self,'Сохранить квитанцию',default,'PDF (*.pdf)')
            if not path:return
            created=create_receipt(data,path);QMessageBox.information(self,'Квитанция сохранена',f"Учебная квитанция сохранена:\n{created}")
        except Exception as e:message_error(self,'Не удалось сформировать квитанцию',e)

    def edit_profile(self):
        try:profile=self.service.user_client_profile(self.user)
        except Exception as e:message_error(self,'Профиль недоступен',e);return
        dlg=QDialog(self);dlg.setWindowTitle('Контактные данные');form=QFormLayout(dlg);first=QLineEdit(profile['first_name']);last=QLineEdit(profile['last_name']);phone=QLineEdit(profile['phone']);birth=QDateEdit();birth.setCalendarPopup(True);birth.setDate(profile['birth_date'] or QDate.currentDate().toPython());form.addRow('Имя',first);form.addRow('Фамилия',last);form.addRow('Телефон',phone);form.addRow('Дата рождения',birth);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.update_client_profile(self.user,first.text(),last.text(),phone.text(),birth.date().toPython());self.refresh_cabinet()
            except Exception as e:message_error(self,'Не удалось сохранить профиль',e)

    def change_password_dialog(self):
        dlg=QDialog(self);dlg.setWindowTitle('Изменить пароль');form=QFormLayout(dlg);old=PasswordLineEdit();new=PasswordLineEdit();confirm=PasswordLineEdit()
        form.addRow('Текущий пароль',old);form.addRow('Новый пароль',new);form.addRow('Повторите новый',confirm);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.change_password(self.user,old.text(),new.text(),confirm.text());QMessageBox.information(self,'Пароль изменён','Новый пароль сохранён.')
            except Exception as e:message_error(self,'Не удалось изменить пароль',e)

    def mark_all_notifications(self):
        if self.user:self.service.mark_notifications_read(self.user);self.refresh_cabinet()

    def build_weather(self):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(28,24,28,20);head=QHBoxLayout();head.addLayout(self.section('Погода и безопасность','Прогноз Open-Meteo · справочная информация, не разрешение на выход.'));head.addStretch();self.weather_button=QPushButton('Обновить прогноз');self.weather_button.clicked.connect(self.refresh_weather_async);head.addWidget(self.weather_button);root.addLayout(head)
        self.weather_banner=QFrame();self.weather_banner.setObjectName('Card');bl=QHBoxLayout(self.weather_banner);self.weather_big=QLabel('Нет свежих данных');self.weather_big.setStyleSheet('font-size:18pt;font-weight:750');bl.addWidget(self.weather_big);self.weather_risk=QLabel('');bl.addStretch();bl.addWidget(self.weather_risk);root.addWidget(self.weather_banner)
        self.weather_metrics=QGridLayout();root.addLayout(self.weather_metrics)
        self.weather_daily=QHBoxLayout();root.addLayout(self.weather_daily)
        self.weather_chart=ChartCanvas();self.weather_chart.setMinimumHeight(300);root.addWidget(self.weather_chart,1)
        self.weather_note=QLabel('Высота волн и период волн показываются только при подключении подходящего морского источника.');self.weather_note.setObjectName('Subtitle');root.addWidget(self.weather_note)
        self.weather_worker=None;return page

    def refresh_weather_card(self):
        try:
            d=self.service.latest_weather()
            if d:self.home_weather.setText(f"{d['temperature']} °C · {weather_condition(d['weather_code'])} · ветер {d['wind_speed']} км/ч · сохранено {pretty(d['observed_at'])} · риск: {self.risk_title(d['safety_level'])}")
            else:self.home_weather.setText('Свежих сохранённых данных нет. Откройте раздел «Погода».')
        except Exception:self.home_weather.setText('Погодные данные пока недоступны.')

    def refresh_weather_async(self):
        if self.weather_worker and self.weather_worker.isRunning():return
        self.weather_button.setEnabled(False);self.weather_button.setText('Загрузка прогноза…')
        self.weather_worker=WeatherWorker(self.service,float(self.settings['latitude']),float(self.settings['longitude']))
        self.weather_worker.result.connect(self.weather_result);self.weather_worker.start()

    def weather_result(self,data,error):
        self.weather_button.setEnabled(True);self.weather_button.setText('Обновить прогноз')
        if error:
            logging.getLogger('yachtclub').error('Weather provider failed: %s',error)
            QMessageBox.warning(self,'Прогноз недоступен','Не удалось получить свежие погодные данные. Показываются последние сохранённые наблюдения.')
        self.refresh_weather_page();self.refresh_weather_card()

    def refresh_weather_page(self):
        try:
            rows=self.service.weather_history(168);now=self.service.latest_weather()
            while self.weather_metrics.count():
                i=self.weather_metrics.takeAt(0);w=i.widget()
                if w:w.deleteLater()
            if now:
                fields=[('Температура',f"{now['temperature']} °C"),('Ветер',f"{now['wind_speed']} км/ч"),('Порывы',f"{now['wind_gust']} км/ч"),('Направление',f"{now['wind_direction']}°"),('Осадки',f"{now['precipitation']} мм · {now['precipitation_probability'] or '—'}%"),('Облачность',f"{now['cloud_cover']}%"),('Видимость',f"{now['visibility_km'] or '—'} км"),('Море','Нет данных')]
                for i,(t,v) in enumerate(fields):self.weather_metrics.addWidget(MetricCard(t,v),i//4,i%4)
                self.weather_big.setText(f"{weather_condition(now['weather_code'])} · {now['temperature']} °C · обновлено {pretty(now['observed_at'])}")
                style,color,_=self.risk_desc(now['safety_level']);self.weather_risk.setText(f"{self.risk_title(now['safety_level'])}\n{self.risk_reason(now['safety_level'])}");self.weather_risk.setStyleSheet(f"font-size:13pt;font-weight:700;color:{color}")
            else:self.weather_big.setText('Нет сохранённых данных. Нажмите «Обновить прогноз».')
            forecast=[r for r in reversed(rows) if r['is_forecast']]
            self.clear_layout(self.weather_daily)
            days={}
            for r in forecast:
                local_time=r['observed_at'].astimezone()
                days.setdefault(local_time.date(),[]).append(r)
            for day,items in list(days.items())[:7]:
                temps=[float(r['temperature']) for r in items if r['temperature'] is not None]
                gusts=[float(r['wind_gust']) for r in items if r['wind_gust'] is not None]
                precip=sum(float(r['precipitation'] or 0) for r in items)
                noon=min(items,key=lambda r:abs(r['observed_at'].astimezone().hour-12))
                f=QFrame();f.setObjectName('Card');v=QVBoxLayout(f)
                weekday=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][day.weekday()]
                v.addWidget(QLabel(f'{weekday}, {day:%d.%m}'))
                v.addWidget(QLabel(f"{min(temps):.0f}° / {max(temps):.0f}°" if temps else 'Нет данных'))
                v.addWidget(QLabel(weather_condition(noon['weather_code'])))
                v.addWidget(QLabel(f"Порывы до {max(gusts):.0f} км/ч" if gusts else 'Ветер: нет данных'))
                v.addWidget(QLabel(f"Осадки {precip:.1f} мм"))
                self.weather_daily.addWidget(f)
            samples=[r for r in reversed(rows) if r['is_forecast']][:48]
            self.weather_chart.figure.clear();axes=self.weather_chart.figure.subplots(1,3)
            if samples:
                times=[r['observed_at'].astimezone().strftime('%H:%M') for r in samples]
                axes[0].plot(times,[r['temperature'] for r in samples],color='#e6a54d');axes[0].set_title('Температура, °C');axes[0].tick_params(axis='x',rotation=65)
                axes[1].plot(times,[r['wind_speed'] for r in samples],label='Ветер',color='#277c9b');axes[1].plot(times,[r['wind_gust'] for r in samples],label='Порывы',color='#e16c59');axes[1].set_title('Ветер, км/ч');axes[1].legend(fontsize=8);axes[1].tick_params(axis='x',rotation=65)
                axes[2].bar(times,[r['precipitation'] or 0 for r in samples],color='#56a89c');axes[2].set_title('Осадки, мм');axes[2].tick_params(axis='x',rotation=65)
            else:
                for ax in axes:ax.text(.5,.5,'Нет прогноза',ha='center',va='center');ax.set_axis_off()
            self.weather_chart.draw()
        except Exception as e:message_error(self,'Не удалось загрузить погоду',e)

    @staticmethod
    def clear_layout(layout):
        while layout.count():
            item=layout.takeAt(0);w=item.widget()
            if w:w.deleteLater()

    @staticmethod
    def risk_title(level):return {'favorable':'Благоприятно','caution':'Внимание','warning':'Ограничения','danger':'Опасно'}.get(level,'Неизвестно')
    @staticmethod
    def risk_desc(level):return level,{'favorable':'#168a85','caution':'#c79221','warning':'#d27a25','danger':'#bf3f45'}.get(level,'#607483'),''
    @staticmethod
    def risk_reason(level):return {'favorable':'Порогов не превышено','caution':'Проверьте ветер и прогноз','warning':'Нужна ручная проверка','danger':'Не подтверждать выход автоматически'}.get(level,'Нет данных')

    def build_admin(self):
        page=QWidget();outer=QHBoxLayout(page);outer.setContentsMargins(0,0,0,0)
        self.admin_sidebar=QFrame();self.admin_sidebar.setObjectName('Sidebar');self.admin_sidebar.setFixedWidth(230);self.admin_sidebar_layout=QVBoxLayout(self.admin_sidebar);brand=QLabel('УПРАВЛЕНИЕ\nКЛУБОМ');brand.setStyleSheet('color:white;font-size:16pt;font-weight:750;padding:14px');self.admin_sidebar_layout.addWidget(brand)
        self.admin_stack=QStackedWidget();self.admin_pages={};self.admin_nav={}
        names=[('Обзор','dashboard','⌂'),('Заявки','applications','▦'),('Флот','fleet','⚓'),('Клиенты','clients','♙'),('Сотрудники','staff','♧'),('Услуги и тарифы','services','◇'),('Порты','ports','⚓'),('Причалы и места','piers','▤'),('Карта портов','portmap','⌖'),('Обслуживание','maintenance','⚙'),('Финансы','finance','₽'),('Погода','weather','☀'),('Аналитика','analytics','▥'),('Уведомления','notifications','♢'),('Журнал действий','audit','◷'),('SQL-консоль','sql','⌘')]
        for title,key,icon in names:
            page_widget=self.admin_page(key,title);self.admin_pages[key]=page_widget;self.admin_stack.addWidget(page_widget)
            btn=QPushButton(f"{icon}   {title}");btn.setObjectName('Nav');btn.clicked.connect(lambda _,k=key:self.show_admin_page(k));self.admin_nav[key]=btn;self.admin_sidebar_layout.addWidget(btn)
        self.admin_sidebar_layout.addStretch();self.admin_staff_label=QLabel('');self.admin_staff_label.setStyleSheet('color:#d3e3eb;padding:12px');self.admin_sidebar_layout.addWidget(self.admin_staff_label)
        password_btn=QPushButton('Сменить пароль');password_btn.setObjectName('Nav');password_btn.clicked.connect(self.change_password_dialog);self.admin_sidebar_layout.addWidget(password_btn)
        exitbtn=QPushButton('← Клиентский режим');exitbtn.setObjectName('Nav');exitbtn.clicked.connect(self.exit_admin);self.admin_sidebar_layout.addWidget(exitbtn)
        self.admin_sidebar.adjustSize();self.admin_sidebar.setMinimumHeight(self.admin_sidebar.sizeHint().height())
        self.admin_sidebar_scroll=QScrollArea();self.admin_sidebar_scroll.setWidgetResizable(True);self.admin_sidebar_scroll.setFrameShape(QFrame.NoFrame);self.admin_sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.admin_sidebar_scroll.setFixedWidth(248);self.admin_sidebar_scroll.setWidget(self.admin_sidebar)
        outer.addWidget(self.admin_sidebar_scroll);content_scroll=QScrollArea();content_scroll.setWidgetResizable(True);content_scroll.setWidget(self.admin_stack);outer.addWidget(content_scroll,1);return page

    def admin_page(self,key,title):
        page=QWidget();root=QVBoxLayout(page);root.setContentsMargins(26,22,26,20);root.setSpacing(14)
        root.addLayout(self.section(title,self.admin_subtitle(key)))
        if key=='dashboard':
            self.admin_metrics=QGridLayout();root.addLayout(self.admin_metrics);self.admin_dashboard_canvas=ChartCanvas();self.admin_dashboard_canvas.setMinimumHeight(270);root.addWidget(self.admin_dashboard_canvas,1);self.admin_alert_table=QTableWidget();root.addWidget(self.admin_alert_table,1)
        elif key=='applications':
            bar=QHBoxLayout();self.app_status=QComboBox()
            for label,code in [('Все',None),('Ожидает подтверждения','pending'),('Подтверждена','confirmed'),('Ожидает оплаты','awaiting_payment'),('Оплачена','paid'),('Активна','active'),('Завершена','completed'),('Отклонена','rejected'),('Отменена','cancelled')]:self.app_status.addItem(label,code)
            self.app_status.currentIndexChanged.connect(lambda:self.refresh_admin_page('applications'));bar.addWidget(self.app_status);refresh=QPushButton('Обновить');refresh.clicked.connect(lambda:self.refresh_admin_page('applications'));bar.addWidget(refresh);bar.addStretch();root.addLayout(bar)
            actions=QHBoxLayout()
            for text,fn in [('Подтвердить',lambda:self.set_application('confirmed')),('Отклонить',lambda:self.set_application('rejected')),('Отметить ожидающей оплаты',lambda:self.set_application('awaiting_payment')),('Место отправления',self.assign_reservation_berth),('Выдать яхту',self.issue_rental),('Принять возврат',self.return_rental)]:
                b=QPushButton(text);b.setObjectName('Secondary' if text!='Подтвердить' else '');b.clicked.connect(fn);actions.addWidget(b)
            root.addLayout(actions);self.app_table=QTableWidget();root.addWidget(self.app_table,1)
        elif key=='fleet':
            bar=QHBoxLayout();self.boat_search=QLineEdit();self.boat_search.setPlaceholderText('Поиск яхты');bar.addWidget(self.boat_search);self.boat_search.textChanged.connect(lambda:self.refresh_admin_page('fleet'))
            for text,fn in [('Добавить яхту',self.add_boat),('Изменить',self.edit_boat),('Фото яхты',self.manage_boat_images),('Архивировать',self.archive_boat),('Переместить',self.assign_boat_berth)]:
                b=QPushButton(text);b.setObjectName('Secondary' if text!='Добавить яхту' else '');b.clicked.connect(fn);bar.addWidget(b)
            root.addLayout(bar);self.boat_table=QTableWidget();root.addWidget(self.boat_table,1)
        elif key=='clients':
            bar=QHBoxLayout();self.client_search=QLineEdit();self.client_search.setPlaceholderText('ФИО, телефон или email');bar.addWidget(self.client_search);self.client_search.textChanged.connect(lambda:self.refresh_admin_page('clients'));edit=QPushButton('Изменить профиль');edit.setObjectName('Secondary');edit.clicked.connect(self.edit_client_profile);bar.addWidget(edit);block=QPushButton('Заблокировать / разблокировать');block.clicked.connect(self.toggle_client_block);bar.addWidget(block);member=QPushButton('Изменить членство');member.setObjectName('Secondary');member.clicked.connect(self.change_membership);bar.addWidget(member);root.addLayout(bar);self.client_table=QTableWidget();root.addWidget(self.client_table,1)
        elif key=='staff':
            bar=QHBoxLayout();add=QPushButton('Создать сотрудника');add.clicked.connect(self.add_staff);bar.addWidget(add);edit=QPushButton('Изменить данные');edit.setObjectName('Secondary');edit.clicked.connect(self.edit_staff);bar.addWidget(edit);deactivate=QPushButton('Активировать / отключить');deactivate.setObjectName('Secondary');deactivate.clicked.connect(self.toggle_staff);bar.addWidget(deactivate);bar.addStretch();root.addLayout(bar);self.staff_table=QTableWidget();root.addWidget(self.staff_table,1)
        elif key=='services':
            bar=QHBoxLayout();add=QPushButton('Добавить услугу');add.clicked.connect(self.edit_service);edit=QPushButton('Изменить выбранную');edit.setObjectName('Secondary');edit.clicked.connect(self.edit_service);bar.addWidget(add);bar.addWidget(edit);bar.addStretch();root.addLayout(bar);self.service_table=QTableWidget();root.addWidget(self.service_table,1)
        elif key=='piers':
            bar=QHBoxLayout();self.piers_port_filter=QComboBox();self.piers_port_filter.addItem('Все порты',None)
            for item in self.db.rows('SELECT port_id,name FROM ports ORDER BY name'):self.piers_port_filter.addItem(item['name'],item['port_id'])
            self.piers_port_filter.currentIndexChanged.connect(lambda:self.refresh_admin_page('piers'));bar.addWidget(QLabel('Порт'));bar.addWidget(self.piers_port_filter)
            pier_add=QPushButton('Добавить причал');pier_add.clicked.connect(self.add_pier);bar.addWidget(pier_add);pier_edit=QPushButton('Изменить причал');pier_edit.setObjectName('Secondary');pier_edit.clicked.connect(self.edit_pier);bar.addWidget(pier_edit);berth_add=QPushButton('Добавить место');berth_add.setObjectName('Secondary');berth_add.clicked.connect(self.edit_berth);bar.addWidget(berth_add);berth_edit=QPushButton('Изменить место / состояние');berth_edit.setObjectName('Secondary');berth_edit.clicked.connect(self.edit_berth);bar.addWidget(berth_edit);assign=QPushButton('Разместить / переместить яхту');assign.clicked.connect(self.assign_boat_berth);bar.addWidget(assign);bar.addStretch();root.addLayout(bar);self.berth_table=QTableWidget();self.berth_table.cellDoubleClicked.connect(lambda *_:self.edit_berth());root.addWidget(self.berth_table,1)
        elif key=='ports':
            bar=QHBoxLayout()
            for text,fn in [('Добавить порт',self.add_port),('Изменить порт',self.edit_port),('Фото порта',self.upload_port_image),('Деактивировать / активировать',self.toggle_port_active)]:
                b=QPushButton(text);b.setObjectName('Secondary' if text!='Добавить порт' else '');b.clicked.connect(fn);bar.addWidget(b)
            bar.addStretch();root.addLayout(bar);self.port_table=QTableWidget();root.addWidget(self.port_table,1)
        elif key=='portmap':
            self.admin_map_metrics=QHBoxLayout();root.addLayout(self.admin_map_metrics)
            bar=QHBoxLayout();self.admin_map_search=QLineEdit();self.admin_map_search.setPlaceholderText('Поиск порта');self.admin_map_search.textChanged.connect(self.filter_admin_port_map);bar.addWidget(self.admin_map_search,2)
            self.admin_map_state=QComboBox()
            for label,value in [('Все состояния','all'),('Есть свободные места','available'),('Частично ограничен','partial'),('Свободных мест нет','full'),('Закрытые порты','closed'),('Нет данных о местах','unknown')]:self.admin_map_state.addItem(label,value)
            self.admin_map_state.currentIndexChanged.connect(self.filter_admin_port_map);bar.addWidget(self.admin_map_state)
            self.admin_map_capacity=QComboBox();self.admin_map_capacity.addItem('Любая загрузка','all');self.admin_map_capacity.addItem('Есть свободные места','free');self.admin_map_capacity.addItem('Нет свободных мест','no_free');self.admin_map_capacity.currentIndexChanged.connect(self.filter_admin_port_map);bar.addWidget(self.admin_map_capacity)
            self.admin_map_city=QComboBox();self.admin_map_city.addItem('Все города','all');self.admin_map_city.currentIndexChanged.connect(self.filter_admin_port_map);bar.addWidget(self.admin_map_city)
            reset=QPushButton('Сбросить');reset.setObjectName('Secondary');reset.clicked.connect(self.reset_admin_port_filters);bar.addWidget(reset)
            zoom=QPushButton('Начальный масштаб');zoom.setObjectName('Secondary');zoom.clicked.connect(lambda:self.admin_portmap.reset_view());bar.addWidget(zoom)
            refresh_map=QPushButton('Обновить');refresh_map.clicked.connect(lambda:self.refresh_admin_page('portmap'));bar.addWidget(refresh_map);root.addLayout(bar)
            body=QHBoxLayout();self.admin_portmap=PortMapWidget();self.admin_portmap.setMinimumHeight(500);self.admin_portmap.portSelected.connect(self.select_admin_map_port);body.addWidget(self.admin_portmap,3)
            side=QFrame();side.setObjectName('Card');side.setMinimumWidth(290);side.setMaximumWidth(365);sv=QVBoxLayout(side);sv.addWidget(QLabel('Порты'))
            self.admin_map_port_list=QListWidget();self.admin_map_port_list.setMaximumHeight(150);self.admin_map_port_list.currentRowChanged.connect(self.select_admin_map_port_from_list);sv.addWidget(self.admin_map_port_list)
            self.admin_map_port_title=QLabel('Выберите порт на карте или в списке');self.admin_map_port_title.setStyleSheet('font-size:15pt;font-weight:700;color:#173c56');self.admin_map_port_title.setWordWrap(True);sv.addWidget(self.admin_map_port_title)
            self.admin_map_port_info=QLabel('');self.admin_map_port_info.setWordWrap(True);sv.addWidget(self.admin_map_port_info,1)
            actions=QGridLayout();self.admin_map_more=QPushButton('Подробнее о порте');self.admin_map_more.clicked.connect(self.open_admin_map_port_details);actions.addWidget(self.admin_map_more,0,0,1,2)
            self.admin_map_piers=QPushButton('Посмотреть причалы');self.admin_map_piers.setObjectName('Secondary');self.admin_map_piers.clicked.connect(lambda:self.open_admin_map_piers(False));actions.addWidget(self.admin_map_piers,1,0)
            self.admin_map_manage=QPushButton('Управление местами');self.admin_map_manage.setObjectName('Secondary');self.admin_map_manage.clicked.connect(lambda:self.open_admin_map_piers(True));actions.addWidget(self.admin_map_manage,1,1)
            self.admin_map_edit=QPushButton('Редактировать порт');self.admin_map_edit.setObjectName('Secondary');self.admin_map_edit.clicked.connect(self.edit_admin_map_port);actions.addWidget(self.admin_map_edit,2,0,1,2)
            sv.addLayout(actions);body.addWidget(side,1);root.addLayout(body,1)
        elif key=='maintenance':
            bar=QHBoxLayout();add=QPushButton('Запланировать обслуживание');add.clicked.connect(self.add_maintenance);bar.addWidget(add);edit=QPushButton('Изменить выбранное');edit.setObjectName('Secondary');edit.clicked.connect(self.edit_maintenance);bar.addWidget(edit);bar.addStretch();root.addLayout(bar);self.maintenance_table=QTableWidget();root.addWidget(self.maintenance_table,1)
        elif key=='finance':
            self.finance_tabs=QTabWidget();pay=QWidget();pl=QVBoxLayout(pay);self.payments_table=QTableWidget();pl.addWidget(self.payments_table,1);pb=QHBoxLayout()
            for text,fn in [('Подтвердить перевод',lambda:self.review_payment(True)),('Отклонить',lambda:self.review_payment(False)),('Оформить возврат',self.refund_payment)]:
                b=QPushButton(text);b.setObjectName('Secondary');b.clicked.connect(fn);pb.addWidget(b)
            pl.addLayout(pb);self.finance_tabs.addTab(pay,'Платежи')
            ref=QWidget();rl=QVBoxLayout(ref);self.refunds_table=QTableWidget();rl.addWidget(self.refunds_table,1);rb=QHBoxLayout()
            for text,ok in [('Подтвердить возврат',True),('Отклонить возврат',False)]:
                b=QPushButton(text);b.clicked.connect(lambda _,v=ok:self.review_refund(v));rb.addWidget(b)
            rl.addLayout(rb);self.finance_tabs.addTab(ref,'Возвраты');root.addWidget(self.finance_tabs,1)
        elif key=='weather':
            bar=QHBoxLayout();self.admin_weather_title=QLabel('Нет свежей погоды');self.admin_weather_title.setStyleSheet('font-size:15pt;font-weight:700');bar.addWidget(self.admin_weather_title);bar.addStretch();self.admin_weather_button=QPushButton('Обновить Open-Meteo');self.admin_weather_button.clicked.connect(self.refresh_weather_async);bar.addWidget(self.admin_weather_button);root.addLayout(bar);self.admin_weather_grid=QGridLayout();root.addLayout(self.admin_weather_grid);self.admin_weather_canvas=ChartCanvas();self.admin_weather_canvas.setFixedHeight(390);root.addWidget(self.admin_weather_canvas)
        elif key=='analytics':
            bar=QHBoxLayout();self.analytics_from=QDateEdit();self.analytics_from.setCalendarPopup(True);self.analytics_from.setDate(QDate.currentDate().addYears(-1));self.analytics_to=QDateEdit();self.analytics_to.setCalendarPopup(True);self.analytics_to.setDate(QDate.currentDate());bar.addWidget(QLabel('С даты'));bar.addWidget(self.analytics_from);bar.addWidget(QLabel('по'));bar.addWidget(self.analytics_to);refresh=QPushButton('Построить');refresh.clicked.connect(self.refresh_analytics);bar.addWidget(refresh)
            for text,fn in [('Excel',lambda:self.export_analytics('xlsx')),('PDF',lambda:self.export_analytics('pdf'))]:
                b=QPushButton(text);b.setObjectName('Secondary');b.clicked.connect(fn);bar.addWidget(b)
            root.addLayout(bar)
            ranking_title=QLabel('Рейтинг яхт по заявкам и выручке');ranking_title.setStyleSheet('font-size:13pt;font-weight:700;color:#153b55;padding-top:4px');root.addWidget(ranking_title)
            self.analytics_table=QTableWidget();self.analytics_table.setMinimumHeight(300);self.analytics_table.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed);root.addWidget(self.analytics_table)
            self.analytics_canvas=ChartCanvas();self.analytics_canvas.setMinimumHeight(1100);root.addWidget(self.analytics_canvas,1)
        elif key=='notifications':
            actions=QHBoxLayout();mark=QPushButton('Отметить выбранное прочитанным');mark.clicked.connect(self.mark_admin_notification);all_read=QPushButton('Отметить всё прочитанным');all_read.setObjectName('Secondary');all_read.clicked.connect(lambda:self.service.mark_notifications_read(self.user) or self.refresh_admin_notifications());actions.addWidget(mark);actions.addWidget(all_read);root.addLayout(actions);self.admin_notification_list=QListWidget();root.addWidget(self.admin_notification_list,1)
        elif key=='audit':
            bar=QHBoxLayout();self.audit_search=QLineEdit();self.audit_search.setPlaceholderText('Пользователь, действие или объект')
            self.audit_from=QDateEdit();self.audit_from.setCalendarPopup(True);self.audit_from.setSpecialValueText('С начала');self.audit_from.setMinimumDate(QDate(2000,1,1));self.audit_from.setDate(QDate(2000,1,1))
            self.audit_to=QDateEdit();self.audit_to.setCalendarPopup(True);self.audit_to.setDate(QDate.currentDate())
            bar.addWidget(self.audit_search,2);bar.addWidget(QLabel('С'));bar.addWidget(self.audit_from);bar.addWidget(QLabel('по'));bar.addWidget(self.audit_to);apply_btn=QPushButton('Применить');apply_btn.clicked.connect(lambda:self.refresh_admin_page('audit'));bar.addWidget(apply_btn);root.addLayout(bar)
            self.audit_search.returnPressed.connect(lambda:self.refresh_admin_page('audit'));self.audit_table=QTableWidget();root.addWidget(self.audit_table,1)
        elif key=='sql':
            warn=QLabel('Выберите подготовленный запрос. Результаты читаются из PostgreSQL; изменение данных через каталог запросов запрещено.');warn.setObjectName('Subtitle');warn.setWordWrap(True);root.addWidget(warn)
            filters=QHBoxLayout();self.sql_category=QComboBox();self.sql_category.addItems(['Простые','Средние','Сложные']);self.sql_query=QComboBox();filters.addWidget(self.sql_category);filters.addWidget(self.sql_query,1);root.addLayout(filters)
            self.sql_description=QLabel();self.sql_description.setWordWrap(True);self.sql_description.setObjectName('Subtitle');root.addWidget(self.sql_description)
            self.sql_category.currentIndexChanged.connect(self.update_sql_presets);self.sql_query.currentIndexChanged.connect(self.update_sql_description)
            self.update_sql_presets()
            self.sql_manual=QGroupBox('Ручной режим · только администратор');self.sql_manual.setCheckable(True);self.sql_manual.setChecked(False);manual_layout=QVBoxLayout(self.sql_manual);self.sql_input=QPlainTextEdit();self.sql_input.setPlaceholderText('SELECT ...');self.sql_input.setMaximumHeight(120);self.sql_input.setVisible(False);manual_layout.addWidget(self.sql_input);self.sql_manual.toggled.connect(self.sql_input.setVisible);root.addWidget(self.sql_manual)
            bar=QHBoxLayout();run=QPushButton('Выполнить запрос');run.clicked.connect(self.run_sql);bar.addWidget(run);self.sql_time=QLabel('');bar.addWidget(self.sql_time);bar.addStretch();root.addLayout(bar);self.sql_result=QTableWidget();root.addWidget(self.sql_result,1)
        return page

    @staticmethod
    def admin_subtitle(key):
        return {'dashboard':'Операционное состояние, поступления и задачи на сегодня','applications':'Очередь заявок и полный цикл обработки заказа','fleet':'Каталог, тарифы, фотографии и размещение судов','clients':'Профили, членство, обращения и задолженности','services':'Прайс-лист с сохранением цены в заказе','ports':'Порты, адреса, контакты и фотографии','piers':'Причалы, места стоянки и размещение яхт','portmap':'Координаты портов, причалов и загруженность стоянок','maintenance':'Плановые работы, ремонты и следующий осмотр','finance':'Платежи, подтверждения, учебные квитанции и возвраты','weather':'Погодные показатели, прогноз и риск по типу судна','analytics':'Периодические показатели клуба с переходом к данным','notifications':'Заявки и платежи, ожидающие решения','audit':'Изменения операционных и финансовых данных','sql':'Исследовательские запросы к PostgreSQL в режиме чтения'}.get(key,'')

    def update_sql_presets(self):
        presets={
          'Простые':[
            ('Все яхты','Данные карточек флота.','SELECT, ORDER BY',"SELECT boat_id,name,model,boat_type,manufacturer,status_name,capacity,daily_rate FROM vw_boat_catalog ORDER BY name"),
            ('Свободные яхты','Яхты со статусом «Свободна».','SELECT, WHERE, ORDER BY',"SELECT boat_id,name,boat_type,capacity,daily_rate FROM vw_boat_catalog WHERE status_name='Свободна' ORDER BY daily_rate"),
            ('Услуги и тарифы','Активные дополнительные услуги.','SELECT, WHERE, ORDER BY',"SELECT name,description,price,pricing_unit FROM services WHERE is_active ORDER BY name"),
            ('Клиенты','Список клиентских профилей.','SELECT, JOIN, ORDER BY',"SELECT c.first_name,c.last_name,c.phone,u.email FROM clients c JOIN users u USING(user_id) ORDER BY c.last_name,c.first_name"),
            ('Бронирования за 30 дней','Заявки, созданные за последний месяц.','SELECT, WHERE, BETWEEN',"SELECT reservation_id,boat_name,client_name,start_at,end_at,status_title FROM vw_active_reservations WHERE created_at::date BETWEEN CURRENT_DATE-30 AND CURRENT_DATE ORDER BY created_at DESC"),
            ('Яхты выбранного типа','Пример фильтра по типу судна.','SELECT, WHERE, DISTINCT',"SELECT boat_id,name,model,boat_type FROM vw_boat_catalog WHERE boat_type=(SELECT name FROM boat_types ORDER BY name LIMIT 1) ORDER BY name")
          ],
          'Средние':[
            ('Заявки с клиентами и яхтами','Связанный список заявок.','JOIN, ORDER BY',"SELECT r.reservation_id,c.first_name||' '||c.last_name AS client,b.name AS boat,r.start_at,r.end_at,r.total_amount,rs.title AS status FROM reservations r JOIN clients c USING(client_id) JOIN boats b USING(boat_id) JOIN reservation_statuses rs ON rs.code=r.status_code ORDER BY r.created_at DESC LIMIT 100"),
            ('Число заявок по клиентам','Клиенты с количеством их заявок.','JOIN, GROUP BY, COUNT',"SELECT c.client_id,c.first_name,c.last_name,count(r.reservation_id) AS bookings FROM clients c LEFT JOIN reservations r USING(client_id) GROUP BY c.client_id ORDER BY bookings DESC"),
            ('Число заявок по яхтам','Спрос по каждому судну.','JOIN, GROUP BY, COUNT',"SELECT b.boat_id,b.name,count(r.reservation_id) AS bookings FROM boats b LEFT JOIN reservations r USING(boat_id) GROUP BY b.boat_id ORDER BY bookings DESC"),
            ('Выручка по месяцам','Подтверждённые платежи с помесячной суммой.','GROUP BY, SUM, FILTER',"SELECT date_trunc('month',confirmed_at)::date AS month_date,sum(amount) FILTER(WHERE status IN('confirmed','partially_refunded')) AS revenue FROM payments WHERE confirmed_at IS NOT NULL GROUP BY 1 ORDER BY 1"),
            ('Яхты с числом заявок выше 2','Суда, превысившие указанный порог.','JOIN, GROUP BY, HAVING, COUNT',"SELECT b.name,count(r.reservation_id) AS bookings FROM boats b JOIN reservations r USING(boat_id) GROUP BY b.boat_id HAVING count(r.reservation_id)>2 ORDER BY bookings DESC"),
            ('Сумма и средний чек по типам','Сравнение выручки между классами судов.','JOIN, GROUP BY, SUM, AVG',"SELECT bt.name,count(r.reservation_id) AS bookings,sum(r.total_amount) AS revenue,avg(r.total_amount) AS average_amount FROM boat_types bt JOIN boats b USING(boat_type_id) JOIN reservations r USING(boat_id) GROUP BY bt.name ORDER BY revenue DESC")
          ],
          'Сложные':[
            ('Клиенты выше среднего расхода','Сравнение с общим средним расходом клиентов.','CTE, подзапрос, AVG',"WITH spend AS(SELECT c.client_id,c.first_name,c.last_name,coalesce(sum(p.amount) FILTER(WHERE p.status IN('confirmed','partially_refunded')),0) AS total_spent FROM clients c LEFT JOIN payments p USING(client_id) GROUP BY c.client_id) SELECT * FROM spend WHERE total_spent>(SELECT avg(total_spent) FROM spend) ORDER BY total_spent DESC"),
            ('Рейтинг яхт по бронированиям','Место судна в рейтинге заявок.','CTE, RANK, COUNT',"WITH demand AS(SELECT b.boat_id,b.name,count(r.reservation_id) AS bookings FROM boats b LEFT JOIN reservations r ON r.boat_id=b.boat_id AND r.status_code NOT IN('cancelled','rejected','expired') GROUP BY b.boat_id) SELECT *,rank() OVER(ORDER BY bookings DESC) AS rank_no FROM demand ORDER BY rank_no,name"),
            ('Сравнение выручки по месяцам','Выручка и разница с предыдущим месяцем.','CTE, LAG, SUM',"WITH m AS(SELECT date_trunc('month',confirmed_at)::date AS month_date,sum(amount) AS revenue FROM payments WHERE status IN('confirmed','partially_refunded') AND confirmed_at IS NOT NULL GROUP BY 1) SELECT month_date,revenue,lag(revenue) OVER(ORDER BY month_date) AS previous_revenue,revenue-lag(revenue) OVER(ORDER BY month_date) AS difference FROM m ORDER BY month_date"),
            ('Яхты без заявок за 90 дней','Суда без новых заявок за выбранный примерный период.','NOT EXISTS',"SELECT b.boat_id,b.name FROM boats b WHERE NOT b.is_archived AND NOT EXISTS(SELECT 1 FROM reservations r WHERE r.boat_id=b.boat_id AND r.created_at>=now()-interval '90 days' AND r.status_code NOT IN('cancelled','rejected')) ORDER BY b.name"),
            ('Загрузка флота','Рассчитанная загрузка по календарному периоду.','Функция, CASE',"SELECT * FROM fn_get_fleet_utilization(CURRENT_DATE-30,CURRENT_DATE) ORDER BY utilization_percent DESC"),
            ('Последняя заявка каждого клиента','Одна самая свежая заявка на клиента.','CTE, ROW_NUMBER',"WITH ranked AS(SELECT r.*,row_number() OVER(PARTITION BY client_id ORDER BY created_at DESC) AS row_no FROM reservations r) SELECT c.first_name,c.last_name,b.name AS boat,r.start_at,r.status_code FROM ranked r JOIN clients c USING(client_id) JOIN boats b USING(boat_id) WHERE r.row_no=1 ORDER BY c.last_name,c.first_name"),
            ('Клиенты без подтверждённых оплат','Клиенты с заявками, по которым нет подтверждённого платежа.','EXISTS, NOT EXISTS',"SELECT DISTINCT c.client_id,c.first_name,c.last_name FROM clients c WHERE EXISTS(SELECT 1 FROM reservations r WHERE r.client_id=c.client_id) AND NOT EXISTS(SELECT 1 FROM payments p WHERE p.client_id=c.client_id AND p.status IN('confirmed','partially_refunded')) ORDER BY c.last_name"),
            ('Выручка по яхтам','Рейтинг судов по сумме заявок и платежей.','JOIN, GROUP BY, SUM, RANK',"WITH rev AS(SELECT b.boat_id,b.name,sum(p.amount) AS revenue FROM boats b JOIN reservations r USING(boat_id) JOIN payments p USING(reservation_id) WHERE p.status IN('confirmed','partially_refunded') GROUP BY b.boat_id) SELECT *,rank() OVER(ORDER BY revenue DESC) AS rank_no FROM rev ORDER BY rank_no")
          ]
        }
        rows=presets[self.sql_category.currentText()] if hasattr(self,'sql_category') else presets['Простые']
        self.sql_query.blockSignals(True);self.sql_query.clear()
        for name,description,features,query in rows:self.sql_query.addItem(name,(description,features,query))
        self.sql_query.blockSignals(False);self.update_sql_description()

    def update_sql_description(self):
        if not hasattr(self,'sql_description') or not self.sql_query.count():return
        description,features,_=self.sql_query.currentData()
        self.sql_description.setText(f'{description} Конструкции: {features}.')

    def show_admin_page(self,key):
        if key in ('sql','audit','staff','ports') and self.user.get('role_name')!='admin':QMessageBox.warning(self,'Недостаточно прав','Раздел доступен только администратору.');return
        self.admin_stack.setCurrentWidget(self.admin_pages[key])
        for k,b in self.admin_nav.items():b.setProperty('active',k==key);b.style().unpolish(b);b.style().polish(b)
        self.refresh_admin_page(key)

    def refresh_admin(self):
        if not hasattr(self,'admin_stack'):return
        self.admin_staff_label.setText(f"{self.user.get('email','')}\nРоль: {pretty(self.user.get('role_name',''))}")
        self.show_admin_page('dashboard')

    def refresh_admin_page(self,key):
        try:
            if key=='dashboard':self.refresh_admin_dashboard()
            elif key=='applications':
                rows=self.service.admin_applications(self.app_status.currentData())
                self.app_table=update_table(self.app_table,rows,[(k,l) for k,l in [('reservation_id','№'),('client_name','Клиент'),('email','Email'),('phone','Телефон'),('boat_name','Яхта'),('start_at','Начало'),('end_at','Окончание'),('port_name','Порт'),('pickup_pier_name','Причал'),('pickup_berth_number','Место'),('passenger_count','Пассажиры'),('total_amount','Сумма'),('status_title','Статус'),('created_at','Заявка'),('paid','Оплачено'),('balance','Остаток'),('customer_comment','Комментарий')]],hidden=('reservation_id',))
            elif key=='fleet':
                rows=self.service.admin_boats(self.boat_search.text());self.boat_table=update_table(self.boat_table,rows,[(k,l) for k,l in [('boat_id','ID'),('name','Яхта'),('model','Модель'),('boat_type','Тип'),('manufacturer','Производитель'),('status_name','Состояние'),('production_year','Год'),('length','Длина'),('width','Ширина'),('capacity','Пассажиры'),('cabin_count','Каюты'),('hourly_rate','Тариф/ч'),('daily_rate','Тариф/сутки'),('is_archived','Архив')]],hidden=('boat_id',))
            elif key=='clients':
                rows=self.service.admin_clients(self.client_search.text());self.client_table=update_table(self.client_table,rows,[(k,l) for k,l in [('client_id','ID'),('first_name','Имя'),('last_name','Фамилия'),('phone','Телефон'),('email','Email'),('membership','Членство'),('end_date','До'),('membership_status','Профиль'),('reservation_count','Заявок'),('balance','Долг'),('is_active','Вход разрешён')]],hidden=('client_id',))
            elif key=='staff':
                rows=self.service.admin_staff();self.staff_table=update_table(self.staff_table,rows,[(k,l) for k,l in [('employee_id','ID'),('email','Email'),('first_name','Имя'),('last_name','Фамилия'),('position_name','Должность'),('role_name','Роль'),('hire_date','Принят'),('is_active','Активен')]],hidden=('employee_id',))
            elif key=='services':
                rows=self.service.admin_services();self.service_table=update_table(self.service_table,rows,[(k,l) for k,l in [('service_id','ID'),('name','Услуга'),('description','Описание'),('price','Цена'),('pricing_unit','Единица'),('is_active','Активна')]],hidden=('service_id',))
            elif key=='piers':
                rows=self.service.berth_board();port_filter=self.piers_port_filter.currentData() if hasattr(self,'piers_port_filter') else None
                if port_filter is not None:rows=[r for r in rows if r['port_id']==port_filter]
                self.berth_table=update_table(self.berth_table,rows,[(k,l) for k,l in [('port_name','Порт'),('pier','Причал'),('berth_number','Место'),('max_length','Длина макс.'),('max_width','Ширина макс.'),('max_draft','Осадка макс.'),('daily_price','Цена/сутки'),('state_ru','Состояние'),('boat_name','Яхта'),('boat_length','Длина яхты'),('boat_width','Ширина яхты'),('boat_draft','Осадка яхты')]],hidden=('port_id','pier_id','berth_id'))
            elif key=='ports':
                rows=self.service.admin_ports(self.user);self.port_table=update_table(self.port_table,rows,[(k,l) for k,l in [('port_id','ID'),('name','Порт'),('address','Адрес'),('city','Город'),('phone','Телефон'),('opening_hours','Режим работы'),('pier_count','Причалы'),('berth_count','Места'),('boat_count','Яхты'),('is_active','Активен'),('is_demonstration','Демо')]],hidden=('port_id',))
            elif key=='portmap':self.refresh_admin_port_map()
            elif key=='maintenance':
                rows=self.service.admin_maintenance();self.maintenance_table=update_table(self.maintenance_table,rows,[(k,l) for k,l in [('maintenance_id','ID'),('boat_name','Яхта'),('type_name','Работа'),('start_at','Начало'),('end_at','Окончание'),('status','Статус'),('cost','Стоимость'),('next_inspection_date','Следующий осмотр'),('employee_email','Сотрудник')]],hidden=('maintenance_id',))
            elif key=='finance':
                rows=self.service.admin_payments();self.payments_table=update_table(self.payments_table,rows,[(k,l) for k,l in [('payment_id','ID'),('reservation_id','Заявка'),('client_name','Клиент'),('boat_name','Яхта'),('method','Способ'),('amount','Сумма'),('status','Статус'),('created_at','Создан'),('confirmed_at','Подтверждён'),('external_reference','Операция'),('is_test','Демо')]],hidden=('payment_id',))
                rf=self.service.admin_refunds();self.refunds_table=update_table(self.refunds_table,rf,[(k,l) for k,l in [('refund_id','ID'),('payment_id','Платёж'),('reservation_id','Заявка'),('client','Клиент'),('amount','Сумма'),('reason','Причина'),('status','Статус'),('created_at','Создан')]],hidden=('refund_id',))
            elif key=='weather':self.refresh_admin_weather()
            elif key=='analytics':self.refresh_analytics()
            elif key=='notifications':self.refresh_admin_notifications()
            elif key=='audit':
                start=self.audit_from.date().toPython() if self.audit_from.date()>self.audit_from.minimumDate() else None
                rows=self.service.admin_audit(self.audit_search.text().strip(),start,self.audit_to.date().toPython());self.audit_table=update_table(self.audit_table,rows,[(k,l) for k,l in [('audit_id','ID'),('email','Пользователь'),('action','Действие'),('entity_type','Объект'),('entity_id','Запись'),('created_at','Время'),('details','Изменения')]],hidden=('audit_id',))
        except Exception as e:message_error(self,'Не удалось обновить раздел',e)

    def refresh_admin_port_map(self):
        self.admin_port_map_rows=self.service.map_ports(include_inactive=True)
        totals={'ports':len(self.admin_port_map_rows),'active':sum(bool(p['is_active']) for p in self.admin_port_map_rows)}
        for key in ('berth_count','free_count','occupied_count','reserved_count','unavailable_count','maintenance_count'):
            totals[key]=sum(int(p.get(key,0) or 0) for p in self.admin_port_map_rows)
        self.admin_map_totals=totals
        cards=[('Всего портов','ports'),('Действующие','active'),('Всего мест','berth_count'),('Свободно','free_count'),('Занято','occupied_count'),('Зарезервировано','reserved_count'),('Недоступно','unavailable_count')]
        while self.admin_map_metrics.count():
            item=self.admin_map_metrics.takeAt(0);widget=item.widget()
            if widget:widget.deleteLater()
        self.admin_map_metric_buttons={}
        for label,key in cards:
            value=totals.get(key,0)
            if key=='unavailable_count':value+=totals.get('maintenance_count',0)
            button=QToolButton();button.setText(f'{label}\n{value}');button.setToolButtonStyle(Qt.ToolButtonTextOnly);button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet('QToolButton{background:#ffffffd9;border:1px solid #d5e7ec;border-radius:12px;padding:9px 12px;color:#173c56;font-weight:650}QToolButton:hover{background:#e3f5f6;border-color:#73bdc5}')
            button.clicked.connect(lambda _=False,k=key:self.set_admin_map_metric_filter(k));self.admin_map_metrics.addWidget(button);self.admin_map_metric_buttons[key]=button
        cities=sorted({str(p.get('city') or '').strip() for p in self.admin_port_map_rows if str(p.get('city') or '').strip()})
        city=self.admin_map_city.currentData() if self.admin_map_city.count() else 'all'
        self.admin_map_city.blockSignals(True);self.admin_map_city.clear();self.admin_map_city.addItem('Все города','all')
        for value in cities:self.admin_map_city.addItem(value,value)
        ix=self.admin_map_city.findData(city)
        if ix>=0:self.admin_map_city.setCurrentIndex(ix)
        self.admin_map_city.blockSignals(False)
        self.filter_admin_port_map()

    def set_admin_map_metric_filter(self,key):
        self.admin_map_metric_filter=key
        self.filter_admin_port_map()

    def filter_admin_port_map(self,*_):
        if not hasattr(self,'admin_portmap') or not hasattr(self,'admin_port_map_rows'):return
        rows=list(self.admin_port_map_rows)
        search=self.admin_map_search.text().strip().casefold()
        state=self.admin_map_state.currentData();city=self.admin_map_city.currentData();capacity=self.admin_map_capacity.currentData()
        if search:rows=[p for p in rows if search in (str(p.get('name') or '')+' '+str(p.get('city') or '')+' '+str(p.get('address') or '')).casefold()]
        if state and state!='all':rows=[p for p in rows if p.get('map_state')==state]
        if city and city!='all':rows=[p for p in rows if p.get('city')==city]
        if capacity=='free':rows=[p for p in rows if p.get('free_count',0)>0]
        elif capacity=='no_free':rows=[p for p in rows if p.get('free_count',0)==0]
        metric=getattr(self,'admin_map_metric_filter','all')
        if metric=='active':rows=[p for p in rows if p.get('is_active')]
        elif metric in ('free_count','occupied_count','reserved_count','unavailable_count'):
            rows=[p for p in rows if p.get(metric,0)>0 or (metric=='unavailable_count' and p.get('maintenance_count',0)>0)]
        elif metric=='berth_count':rows=[p for p in rows if p.get('berth_count',0)>0]
        current_id=getattr(self,'admin_map_selected_id',None)
        if current_id not in [p['port_id'] for p in rows]:current_id=None;self.admin_map_selected_id=None
        self.admin_portmap.set_ports(rows,selected_id=current_id)
        self.admin_map_port_list.blockSignals(True);self.admin_map_port_list.clear()
        for p in rows:
            suffix=f" · свободно {p.get('free_count',0)} из {p.get('berth_count',0)}"
            if not p.get('is_active'):suffix+=' · закрыт'
            elif p.get('map_state')=='unknown':suffix+=' · нет данных о местах'
            item=QListWidgetItem(str(p['name'])+suffix);item.setData(Qt.UserRole,p['port_id']);self.admin_map_port_list.addItem(item)
        if current_id is not None:
            for index in range(self.admin_map_port_list.count()):
                if self.admin_map_port_list.item(index).data(Qt.UserRole)==current_id:self.admin_map_port_list.setCurrentRow(index);break
        self.admin_map_port_list.blockSignals(False)
        if current_id is not None:self.select_admin_map_port(current_id)
        else:
            self.admin_map_port_title.setText('Выберите порт на карте или в списке')
            self.admin_map_port_info.setText(f'Показано портов: {len(rows)} из {len(self.admin_port_map_rows)}')

    def reset_admin_port_filters(self):
        self.admin_map_search.clear();self.admin_map_state.setCurrentIndex(0);self.admin_map_capacity.setCurrentIndex(0);self.admin_map_city.setCurrentIndex(0);self.admin_map_metric_filter='all';self.filter_admin_port_map()

    def select_admin_map_port_from_list(self,row):
        if row<0 or row>=self.admin_map_port_list.count():return
        self.select_admin_map_port(self.admin_map_port_list.item(row).data(Qt.UserRole))

    def select_admin_map_port(self,port_id):
        port=next((p for p in getattr(self,'admin_port_map_rows',[]) if p['port_id']==port_id),None)
        if not port:return
        self.admin_map_selected_id=port_id
        self.admin_portmap.show_port_details(port_id)
        for index in range(self.admin_map_port_list.count()):
            if self.admin_map_port_list.item(index).data(Qt.UserRole)==port_id:
                self.admin_map_port_list.blockSignals(True);self.admin_map_port_list.setCurrentRow(index);self.admin_map_port_list.blockSignals(False);break
        self.admin_map_port_title.setText(port['name'])
        status=port.get('map_state_ru','Нет данных')
        address=', '.join(x for x in (port.get('address'),port.get('city')) if x) or 'Адрес не указан'
        info=(f'<b>{html_escape(status)}</b><br>{html_escape(address)}<br>'
              f'Причалы: {port.get("pier_count",0)} · мест: {port.get("berth_count",0)}<br>'
              f'🟢 Свободно: {port.get("free_count",0)}<br>🔴 Занято: {port.get("occupied_count",0)}<br>'
              f'🟠 Зарезервировано: {port.get("reserved_count",0)}<br>⚪ Недоступно / обслуживание: {port.get("unavailable_count",0)+port.get("maintenance_count",0)}<br>'
              f'Контакт: {html_escape(str(port.get("phone") or "не указан"))}<br>Режим: {html_escape(str(port.get("opening_hours") or "не указан"))}')
        if port.get('description'):info+='<p>'+html_escape(port['description'])+'</p>'
        if port.get('is_demonstration'):info+='<p><i>Демонстрационная запись базы</i></p>'
        self.admin_map_port_info.setText(info)

    def open_admin_map_port_details(self):
        port=next((p for p in getattr(self,'admin_port_map_rows',[]) if p['port_id']==getattr(self,'admin_map_selected_id',None)),None)
        if not port:QMessageBox.information(self,'Выберите порт','Сначала выберите порт на карте или в списке.');return
        dlg=QDialog(self);dlg.setWindowTitle('Информация о порте');dlg.resize(760,560);layout=QVBoxLayout(dlg);scroll=QScrollArea();scroll.setWidgetResizable(True);host=QWidget();box=QVBoxLayout(host)
        title=QLabel(port['name']);title.setStyleSheet('font-size:18pt;font-weight:700;color:#173c56');box.addWidget(title)
        if port.get('cover'):
            image_path=Path(str(port['cover']));image_path=image_path if image_path.is_absolute() else ROOT/image_path
            if image_path.exists():
                photo=QLabel();photo.setPixmap(QPixmap(str(image_path)).scaled(640,250,Qt.KeepAspectRatio,Qt.SmoothTransformation));box.addWidget(photo)
        address=', '.join(x for x in (port.get('address'),port.get('city')) if x) or 'Не указан'
        coords=(f"{port['latitude']}, {port['longitude']}" if port.get('latitude') is not None and port.get('longitude') is not None else 'Не заданы')
        for label,value in [('Статус',port.get('map_state_ru','Нет данных')),('Адрес',address),('Описание',port.get('description') or 'Не указано'),('Телефон',port.get('phone') or 'Не указан'),('Часы работы',port.get('opening_hours') or 'Не указаны'),('Координаты',coords),('Причалы',port.get('pier_count',0)),('Места стоянки',port.get('berth_count',0)),('Свободно / занято / резерв / недоступно',f"{port.get('free_count',0)} / {port.get('occupied_count',0)} / {port.get('reserved_count',0)} / {port.get('unavailable_count',0)+port.get('maintenance_count',0)}")]:
            line=QLabel(f'<b>{html_escape(str(label))}:</b> {html_escape(str(value))}');line.setWordWrap(True);box.addWidget(line)
        table=QTableWidget();items=port.get('berths',[]);table.setRowCount(len(items));table.setColumnCount(6);table.setHorizontalHeaderLabels(['Причал','Место','Статус','Яхта','Длина макс.','Осадка макс.'])
        for row,b in enumerate(items):
            for col,key in enumerate(('pier','number','state_ru','boat_name','max_length','max_draft')):table.setItem(row,col,QTableWidgetItem(str(b.get(key) or '—')))
        table.resizeColumnsToContents();table.setMinimumHeight(min(280,max(90,38*(len(items)+1))));box.addWidget(table);scroll.setWidget(host);layout.addWidget(scroll);buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dlg.reject);buttons.accepted.connect(dlg.accept);layout.addWidget(buttons);dlg.exec()

    def open_admin_map_piers(self,manage=False):
        port_id=getattr(self,'admin_map_selected_id',None)
        if not port_id:QMessageBox.information(self,'Выберите порт','Сначала выберите порт на карте или в списке.');return
        if hasattr(self,'piers_port_filter'):
            index=self.piers_port_filter.findData(port_id)
            if index>=0:self.piers_port_filter.setCurrentIndex(index)
        self.show_admin_page('piers')
        if manage and hasattr(self,'berth_table') and self.berth_table.rowCount():self.berth_table.selectRow(0)

    def edit_admin_map_port(self):
        port_id=getattr(self,'admin_map_selected_id',None)
        if not port_id:QMessageBox.information(self,'Выберите порт','Сначала выберите порт на карте или в списке.');return
        self._save_port_dialog(port_id)

    def refresh_admin_dashboard(self):
        data=self.service.admin_dashboard()
        while self.admin_metrics.count():
            it=self.admin_metrics.takeAt(0);w=it.widget()
            if w:w.deleteLater()
        fields=[('Доход сегодня',money(data['revenue_today'])),('Доход за месяц',money(data['revenue_month'])),('Новые заявки',data['new_requests']),('Ожидают оплаты',data['awaiting_payment']),('Активные аренды',data['active_rentals']),('Свободные яхты',data['free_boats']),('Обслуживание',data['maintenance']),('Заявки с остатком',data['debt_orders'])]
        for i,(label,val) in enumerate(fields):self.admin_metrics.addWidget(MetricCard(label,val),i//4,i%4)
        chart=self.admin_dashboard_canvas.figure;chart.clear();a1,a2=chart.subplots(1,2)
        try:
            rev=self.db.rows("SELECT * FROM fn_get_monthly_revenue((CURRENT_DATE-interval '1 year')::date,CURRENT_DATE)")
            if rev:a1.plot([pretty(r['month']) for r in rev],[float(r['revenue']) for r in rev],marker='o',color='#137f91');a1.set_title('Выручка по месяцам, ₽');a1.tick_params(axis='x',rotation=45)
            else:a1.text(.5,.5,'Нет данных о поступлениях',ha='center',va='center');a1.set_axis_off()
        except Exception as exc:
            logging.getLogger('yachtclub').exception('Не удалось построить график выручки')
            a1.text(.5,.5,'График выручки временно недоступен',ha='center',va='center');a1.set_axis_off()
        try:
            statuses=self.db.rows('SELECT status_code,count(*) count FROM reservations GROUP BY status_code')
            if statuses:a2.pie([r['count'] for r in statuses],labels=[pretty(r['status_code']) for r in statuses],autopct='%1.0f%%',wedgeprops={'width':.42});a2.set_title('Статусы заявок')
            else:a2.text(.5,.5,'Нет заявок',ha='center',va='center');a2.set_axis_off()
        except Exception:
            logging.getLogger('yachtclub').exception('Не удалось построить график статусов')
            a2.text(.5,.5,'Распределение заявок временно недоступно',ha='center',va='center');a2.set_axis_off()
        self.admin_dashboard_canvas.draw()
        alerts=self.service.admin_alerts();self.admin_alert_table=update_table(self.admin_alert_table,alerts,[('title','Событие'),('message','Описание'),('entity','Тип'),('id','Запись'),('created_at','Время')],hidden=('entity','id'))

    def selected_admin_reservation(self):return selected(self.app_table,'reservation_id') if hasattr(self,'app_table') else None

    def set_application(self,status):
        rid=self.selected_admin_reservation()
        if not rid:QMessageBox.information(self,'Выберите заявку','Сначала выберите строку.');return
        note=''
        if status=='rejected':
            note,ok=QInputDialog.getText(self,'Причина отказа','Укажите причину для клиента:')
            if not ok:return
            if not note.strip():QMessageBox.warning(self,'Нужна причина','Укажите причину отказа.');return
        try:self.service.change_reservation_status(self.user,rid,status,note);self.refresh_admin_page('applications');self.refresh_admin_page('portmap');self.refresh_admin_page('piers')
        except Exception as e:message_error(self,'Не удалось изменить статус заявки',e)

    def issue_rental(self):
        rid=self.selected_admin_reservation()
        if not rid:return
        note,ok=QInputDialog.getText(self,'Выдать яхту','Состояние судна при выдаче:')
        if not ok:return
        try:self.service.mark_rental_issued(self.user,rid,note);self.refresh_admin_page('applications');self.refresh_admin_page('portmap');self.refresh_admin_page('piers')
        except Exception as e:message_error(self,'Не удалось выдать яхту',e)

    def return_rental(self):
        rid=self.selected_admin_reservation()
        if not rid:return
        note,ok=QInputDialog.getText(self,'Возврат яхты','Состояние судна при возврате:')
        if not ok:return
        try:self.service.mark_rental_returned(self.user,rid,note);self.refresh_admin_page('applications');self.refresh_admin_page('portmap');self.refresh_admin_page('piers')
        except Exception as e:message_error(self,'Не удалось принять яхту',e)

    def add_boat(self):
        try:
            dlg=BoatDialog(self.service,parent=self)
            if dlg.exec()==QDialog.Accepted:
                bid=self.service.save_boat(self.user,dlg.values())
                if dlg.selected_image_paths:self.add_boat_images(bid,dlg.selected_image_paths,refresh=False)
                self.refresh_admin_page('fleet')
        except Exception as e:message_error(self,'Не удалось добавить яхту',e)

    def edit_boat(self):
        bid=selected(self.boat_table,'boat_id')
        if not bid:QMessageBox.information(self,'Выберите яхту','Сначала выберите яхту.');return
        try:
            row=self.db.one('SELECT * FROM boats WHERE boat_id=%s',(bid,));dlg=BoatDialog(self.service,row,self)
            if dlg.exec()==QDialog.Accepted:
                self.service.save_boat(self.user,dlg.values(),bid)
                if dlg.selected_image_paths:self.add_boat_images(bid,dlg.selected_image_paths,refresh=False)
                self.refresh_admin_page('fleet')
        except Exception as e:message_error(self,'Не удалось изменить яхту',e)

    def archive_boat(self):
        bid=selected(self.boat_table,'boat_id')
        if bid and QMessageBox.question(self,'Архивировать яхту?','Она останется в истории операций и исчезнет из каталога.')==QMessageBox.Yes:
            try:self.service.archive_boat(self.user,bid);self.refresh_admin_page('fleet')
            except Exception as e:message_error(self,'Не удалось архивировать яхту',e)

    def add_boat_images(self,boat_id=None,paths=None,refresh=True):
        bid=boat_id or selected(self.boat_table,'boat_id')
        if not bid:QMessageBox.information(self,'Выберите яхту','Выберите яхту, затем добавьте изображения.');return
        if paths is None:paths,_=QFileDialog.getOpenFileNames(self,'Выберите фотографии яхты с компьютера','','Images (*.png *.jpg *.jpeg *.webp)')
        if not paths:return
        try:
            from PIL import Image
            import uuid
            folder=ROOT/'assets'/'uploads';folder.mkdir(parents=True,exist_ok=True)
            next_order=int(self.db.value('SELECT COALESCE(max(sort_order),0)+1 FROM boat_images WHERE boat_id=%s',(bid,)) or 1)
            prepared=[]
            for ix,src in enumerate(paths):
                image=Image.open(src);image.verify();ext=Path(src).suffix.lower()
                if ext=='.webp':ext='.jpg'
                name=f"boat_{bid}_{uuid.uuid4().hex[:10]}{ext}";target=folder/name
                image=Image.open(src)
                if ext in ('.jpg','.jpeg') and image.mode not in ('RGB','L'):image=image.convert('RGB')
                image.thumbnail((1800,1200));image.save(target,quality=88 if ext in ('.jpg','.jpeg') else None)
                prepared.append((str(target.relative_to(ROOT)).replace('\\','/'),Path(src).stem,next_order+ix,ix==0))
            with self.db.transaction(self.user['user_id']) as tx:
                tx.execute('UPDATE boat_images SET is_cover=false WHERE boat_id=%s',(bid,))
                for image_path,caption,sort_order,is_cover in prepared:
                    tx.execute('INSERT INTO boat_images(boat_id,image_path,caption,alt_text,sort_order,is_cover,source_note) VALUES(%s,%s,%s,%s,%s,%s,%s)',(bid,image_path,caption,caption,sort_order,is_cover,'Загружено администратором'))
            if refresh:self.refresh_admin_page('fleet')
        except Exception as e:message_error(self,'Не удалось загрузить фотографии',e)

    def manage_boat_images(self):
        bid=selected(self.boat_table,'boat_id')
        if not bid:QMessageBox.information(self,'Выберите яхту','Выберите яхту, чтобы загрузить или изменить её фото.');return
        try:
            action,ok=QInputDialog.getItem(self,'Фото яхты','Выберите действие:',('Добавить фотографии с компьютера','Сменить обложку галереи','Удалить фотографию'),0,False)
            if not ok:return
            if action=='Добавить фотографии с компьютера':self.add_boat_images(bid);return
            images=self.db.rows('SELECT image_id,caption,image_path,is_cover FROM boat_images WHERE boat_id=%s ORDER BY is_cover DESC,sort_order,image_id',(bid,))
            if not images:QMessageBox.information(self,'Фото яхты','Для этой яхты ещё не загружены фотографии.');return
            labels=[f"{'★ ' if im['is_cover'] else ''}{im['caption'] or Path(im['image_path']).name}" for im in images]
            label,ok=QInputDialog.getItem(self,'Фото яхты','Выберите изображение:',labels,0,False)
            if not ok:return
            image=images[labels.index(label)]
            if action=='Сменить обложку галереи':self.service.set_boat_cover(self.user,image['image_id'])
            elif QMessageBox.question(self,'Удалить фотографию?','Удалить выбранную фотографию из карточки яхты?')==QMessageBox.Yes:self.service.delete_boat_image(self.user,image['image_id'])
            self.refresh_admin_page('fleet')
        except Exception as e:message_error(self,'Не удалось изменить галерею',e)

    def edit_service(self):
        sid=selected(self.service_table,'service_id') if hasattr(self,'service_table') else None
        row=self.db.one('SELECT * FROM services WHERE service_id=%s',(sid,)) if sid else None;dlg=ServiceDialog(row,self)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.save_service(self.user,dlg.values(),sid);self.refresh_admin_page('services')
            except Exception as e:message_error(self,'Не удалось сохранить услугу',e)

    def toggle_client_block(self):
        cid=selected(self.client_table,'client_id')
        if not cid:return
        row=next((r for r in self.service.admin_clients(self.client_search.text()) if r['client_id']==cid),None)
        blocked=bool(row and row['is_active'])
        reason=''
        if blocked:
            reason,ok=QInputDialog.getText(self,'Блокировка','Укажите причину блокировки:')
            if not ok:return
        try:self.service.set_client_blocked(self.user,cid,blocked,reason);self.refresh_admin_page('clients')
        except Exception as e:message_error(self,'Не удалось изменить доступ',e)

    def edit_client_profile(self):
        cid=selected(self.client_table,'client_id')
        if not cid:QMessageBox.information(self,'Выберите клиента','Выберите клиента в таблице.');return
        row=next((r for r in self.service.admin_clients(self.client_search.text()) if r['client_id']==cid),None)
        if not row:return
        dlg=QDialog(self);dlg.setWindowTitle('Профиль клиента');form=QFormLayout(dlg);first=QLineEdit(row['first_name']);last=QLineEdit(row['last_name']);phone=QLineEdit(row['phone']);email=QLineEdit(row['email'])
        for label,w in [('Имя',first),('Фамилия',last),('Телефон',phone),('Email',email)]:form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.update_client_profile(self.user,cid,first.text(),last.text(),phone.text(),email.text());self.refresh_admin_page('clients')
            except Exception as e:message_error(self,'Не удалось изменить профиль клиента',e)

    def change_membership(self):
        cid=selected(self.client_table,'client_id')
        if not cid:return
        dlg=QDialog(self);dlg.setWindowTitle('Членство клиента');form=QFormLayout(dlg);types=QComboBox()
        for item in self.db.rows('SELECT membership_type_id,name FROM membership_types ORDER BY annual_price'):types.addItem(item['name'],item['membership_type_id'])
        end=QDateEdit();end.setCalendarPopup(True);end.setDate(QDate.currentDate().addYears(1));form.addRow('Уровень',types);form.addRow('Действует до',end);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.set_membership(self.user,cid,types.currentData(),end.date().toPython());self.refresh_admin_page('clients')
            except Exception as e:message_error(self,'Не удалось изменить членство',e)

    def add_port(self):self._save_port_dialog(None)

    def edit_port(self,_checked=False):
        pid=selected(self.port_table,'port_id') if hasattr(self,'port_table') and self.port_table.currentRow()>=0 else None
        if not pid:QMessageBox.information(self,'Выберите порт','Выберите порт в списке.');return
        self._save_port_dialog(pid)

    def _save_port_dialog(self,pid):
        row=self.db.one('SELECT * FROM ports WHERE port_id=%s',(pid,)) if pid else None
        dlg=PortDialog(row,self)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.save_port(self.user,dlg.values(),pid);self.refresh_admin_page('ports');self.refresh_admin_page('piers');self.refresh_admin_page('portmap')
            except Exception as e:message_error(self,'Не удалось сохранить порт',e)

    def toggle_port_active(self):
        pid=selected(self.port_table,'port_id') if hasattr(self,'port_table') else None
        if not pid:QMessageBox.information(self,'Выберите порт','Выберите порт в таблице.');return
        row=self.db.one('SELECT * FROM ports WHERE port_id=%s',(pid,))
        if not row:return
        dlg=PortDialog(row,self);dlg.setWindowTitle('Изменение активности порта');dlg.active.setChecked(not row['is_active'])
        if dlg.exec()==QDialog.Accepted:
            try:self.service.save_port(self.user,dlg.values(),pid);self.refresh_admin_page('ports');self.refresh_admin_page('portmap')
            except Exception as e:message_error(self,'Не удалось изменить статус порта',e)

    def upload_port_image(self):
        pid=selected(self.port_table,'port_id') if hasattr(self,'port_table') else None
        if not pid:QMessageBox.information(self,'Выберите порт','Выберите порт перед загрузкой фото.');return
        path,_=QFileDialog.getOpenFileName(self,'Фотография порта','','Images (*.png *.jpg *.jpeg *.webp)')
        if not path:return
        try:
            from PIL import Image
            import uuid
            source=Image.open(path);source.verify();image=Image.open(path);ext=Path(path).suffix.lower()
            if ext=='.webp':ext='.jpg'
            if ext in ('.jpg','.jpeg') and image.mode not in ('RGB','L'):image=image.convert('RGB')
            image.thumbnail((1800,1200));folder=ROOT/'assets'/'uploads';folder.mkdir(parents=True,exist_ok=True);target=folder/f"port_{pid}_{uuid.uuid4().hex[:10]}{ext}"
            image.save(target,quality=88 if ext in ('.jpg','.jpeg') else None)
            self.service.add_port_image(self.user,pid,str(target.relative_to(ROOT)).replace('\\','/'),Path(path).stem);self.refresh_admin_page('portmap')
        except Exception as e:message_error(self,'Не удалось сохранить фото порта',e)

    def assign_boat_berth(self):
        bid=selected(self.boat_table,'boat_id') if hasattr(self,'boat_table') and self.boat_table.currentRow()>=0 else None
        if not bid:
            bid,ok=QInputDialog.getInt(self,'Размещение яхты','ID яхты:')
            if not ok:return
        try:
            choices=self.db.rows('SELECT b.berth_id,pt.name||\' · \'||p.name||\' · место \'||b.berth_number label FROM berths b JOIN piers p USING(pier_id) JOIN ports pt USING(port_id) WHERE b.status=\'active\' AND pt.is_active AND NOT EXISTS(SELECT 1 FROM boats x WHERE x.current_berth_id=b.berth_id AND NOT x.is_archived) AND NOT EXISTS(SELECT 1 FROM reservations r WHERE r.pickup_berth_id=b.berth_id AND r.status_code IN(\'confirmed\',\'awaiting_payment\',\'paid\',\'active\') AND r.end_at>now()) ORDER BY pt.name,p.name,b.berth_number')
            if not choices:raise ValueError('Нет свободных мест.')
            labels=[r['label'] for r in choices];label,ok=QInputDialog.getItem(self,'Выберите причал','Свободное место:',labels,0,False)
            if not ok:return
            berth=next(r['berth_id'] for r in choices if r['label']==label)
            self.service.assign_berth(self.user,bid,berth);self.refresh_admin_page('piers');self.refresh_admin_page('portmap')
        except Exception as e:message_error(self,'Не удалось разместить яхту',e)

    def assign_reservation_berth(self):
        rid=self.selected_admin_reservation()
        if not rid:QMessageBox.information(self,'Выберите заявку','Выберите подтверждённую заявку.');return
        try:
            choices=self.service.pickup_berth_options(self.user,rid)
            if not choices:raise ValueError('Нет подходящих свободных мест. Сначала проверьте, что у яхты есть активный порт и совместимое место стоянки.')
            labels=[r['label'] for r in choices];label,ok=QInputDialog.getItem(self,'Место отправления','Порт, причал и стоянка:',labels,0,False)
            if not ok:return
            self.service.assign_pickup_berth(self.user,rid,next(r['berth_id'] for r in choices if r['label']==label));self.refresh_admin_page('applications');self.refresh_admin_page('portmap');self.refresh_admin_page('piers')
        except Exception as e:message_error(self,'Не удалось назначить место отправления',e)

    def add_pier(self):self.edit_pier(None)

    def edit_pier(self,_unused=None):
        rownum=self.berth_table.currentRow() if hasattr(self,'berth_table') else -1
        current=None
        if rownum>=0:
            pid=selected(self.berth_table,'pier_id')
            if pid:current=self.db.one('SELECT * FROM piers WHERE pier_id=%s',(pid,))
        dlg=QDialog(self);dlg.setWindowTitle('Изменить причал' if current else 'Новый причал');form=QFormLayout(dlg);port=QComboBox()
        for item in self.db.rows('SELECT port_id,name FROM ports ORDER BY is_active DESC,name'):port.addItem(item['name'],item['port_id'])
        ix=port.findData((current or {}).get('port_id'))
        if ix>=0:port.setCurrentIndex(ix)
        name=QLineEdit(str((current or {}).get('name','')));location=QLineEdit(str((current or {}).get('location','')));desc=QTextEdit();desc.setMaximumHeight(100);desc.setPlainText(str((current or {}).get('description','')))
        active=QCheckBox('Причал активен');active.setChecked(bool((current or {}).get('is_active',True)))
        form.addRow('Порт',port);form.addRow('Название',name);form.addRow('Расположение',location);form.addRow('Описание',desc);form.addRow(active);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.save_pier(self.user,{'name':name.text(),'location':location.text(),'description':desc.toPlainText(),'port_id':port.currentData(),'is_active':active.isChecked()},(current or {}).get('pier_id'));self.refresh_admin_page('piers');self.refresh_admin_page('portmap')
            except Exception as e:message_error(self,'Не удалось сохранить причал',e)

    def edit_berth(self):
        berth_id=selected(self.berth_table,'berth_id') if hasattr(self,'berth_table') else None
        current=self.db.one('SELECT * FROM berths WHERE berth_id=%s',(berth_id,)) if berth_id else None
        dlg=QDialog(self);dlg.setWindowTitle('Изменить место стоянки' if current else 'Новое место стоянки');dlg.resize(440,450);form=QFormLayout(dlg);pier=QComboBox()
        for item in self.db.rows('SELECT pier_id,name FROM piers ORDER BY name'):pier.addItem(item['name'],item['pier_id'])
        ix=pier.findData((current or {}).get('pier_id'))
        if ix>=0:pier.setCurrentIndex(ix)
        number=QLineEdit(str((current or {}).get('berth_number','')));form.addRow('Причал',pier);form.addRow('Номер места',number);spins=[]
        for key,label,default,maxval in [('max_length','Длина, м',25,200),('max_width','Ширина, м',8,50),('max_draft','Осадка, м',4,30),('daily_price','Цена в сутки, ₽',0,10000000)]:
            s=QDoubleSpinBox();s.setRange(0 if key=='daily_price' else .1,maxval);s.setDecimals(2);s.setValue(float((current or {}).get(key) or default));spins.append(s);form.addRow(label,s)
        status=QComboBox()
        for code,label in [('active','Доступно'),('maintenance','На обслуживании'),('closed','Закрыто')]:status.addItem(label,code)
        ix=status.findData((current or {}).get('status'))
        if ix>=0:status.setCurrentIndex(ix)
        form.addRow('Статус',status);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.save_berth(self.user,{'pier_id':pier.currentData(),'berth_number':number.text(),'max_length':spins[0].value(),'max_width':spins[1].value(),'max_draft':spins[2].value(),'daily_price':spins[3].value(),'status':status.currentData()},berth_id);self.refresh_admin_page('piers');self.refresh_admin_page('portmap')
            except Exception as e:message_error(self,'Не удалось сохранить место',e)

    def add_maintenance(self,row=None):
        row=row or {};dlg=QDialog(self);dlg.setWindowTitle('Изменить обслуживание' if row else 'Запланировать обслуживание');dlg.resize(520,520);form=QFormLayout(dlg)
        boats=QComboBox()
        for b in self.db.rows('SELECT boat_id,name FROM boats WHERE NOT is_archived ORDER BY name'):boats.addItem(b['name'],b['boat_id'])
        idx=boats.findData(row.get('boat_id'))
        if idx>=0:boats.setCurrentIndex(idx)
        types=QComboBox()
        for t in self.db.rows('SELECT maintenance_type_id,name FROM maintenance_types ORDER BY name'):types.addItem(t['name'],t['maintenance_type_id'])
        idx=types.findData(row.get('type_id'))
        if idx>=0:types.setCurrentIndex(idx)
        start=QDateEdit();start.setCalendarPopup(True);start.setDate(QDate.fromString(str(row.get('start_at') or QDate.currentDate().toString('yyyy-MM-dd'))[:10],'yyyy-MM-dd'));end=QDateEdit();end.setCalendarPopup(True);end.setSpecialValueText('Не указано');end.setDate(QDate.fromString(str(row.get('end_at') or QDate.currentDate().addDays(1).toString('yyyy-MM-dd'))[:10],'yyyy-MM-dd'));desc=QTextEdit();desc.setMaximumHeight(75);desc.setPlainText(str(row.get('description') or ''));work=QTextEdit();work.setMaximumHeight(75);work.setPlainText(str(row.get('work_performed') or ''));cost=QDoubleSpinBox();cost.setRange(0,100000000);cost.setDecimals(2);cost.setValue(float(row.get('cost') or 0));status=QComboBox()
        for code,title in [('planned','Запланировано'),('in_progress','Выполняется'),('completed','Завершено'),('cancelled','Отменено')]:status.addItem(title,code)
        idx=status.findData(row.get('status'))
        if idx>=0:status.setCurrentIndex(idx)
        inspection=QDateEdit();inspection.setCalendarPopup(True);inspection.setSpecialValueText('Не указано');inspection.setDate(QDate.fromString(str(row.get('next_inspection_date') or QDate.currentDate().addYears(1).toString('yyyy-MM-dd'))[:10],'yyyy-MM-dd'))
        for lab,w in [('Яхта',boats),('Вид работ',types),('Начало',start),('Окончание',end),('Описание',desc),('Выполненные работы',work),('Стоимость',cost),('Статус',status),('Следующий осмотр',inspection)]:form.addRow(lab,w)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.save_maintenance(self.user,{'boat_id':boats.currentData(),'type_id':types.currentData(),'start_at':start.date().toPython(),'end_at':end.date().toPython(),'description':desc.toPlainText(),'work_performed':work.toPlainText(),'cost':cost.value(),'status':status.currentData(),'next_inspection_date':inspection.date().toPython()},row.get('maintenance_id'));self.refresh_admin_page('maintenance')
            except Exception as e:message_error(self,'Не удалось сохранить обслуживание',e)

    def edit_maintenance(self):
        mid=selected(self.maintenance_table,'maintenance_id')
        if not mid:QMessageBox.information(self,'Выберите запись','Выберите запись обслуживания.');return
        try:self.add_maintenance(self.db.one('SELECT * FROM maintenance WHERE maintenance_id=%s',(mid,)))
        except Exception as e:message_error(self,'Не удалось открыть обслуживание',e)

    def add_staff(self):
        dlg=StaffDialog(self.service,self)
        if dlg.exec()==QDialog.Accepted:
            try:self.service.create_staff(self.user,dlg.first.text(),dlg.last.text(),dlg.email.text(),dlg.password.text(),dlg.position.currentData(),dlg.role.currentData());self.refresh_admin_page('staff');QMessageBox.information(self,'Сотрудник создан','Создана учётная запись. Передайте пароль сотруднику безопасным способом.')
            except Exception as e:message_error(self,'Не удалось создать сотрудника',e)

    def edit_staff(self):
        eid=selected(self.staff_table,'employee_id')
        if not eid:QMessageBox.information(self,'Выберите сотрудника','Выберите сотрудника в таблице.');return
        try:
            row=self.db.one('SELECT e.employee_id,e.position_id,e.first_name,e.last_name,u.email,r.role_name FROM employees e JOIN users u USING(user_id) JOIN roles r USING(role_id) WHERE e.employee_id=%s',(eid,));dlg=StaffDialog(self.service,row,self)
            if dlg.exec()==QDialog.Accepted:self.service.update_staff(self.user,eid,{'first_name':dlg.first.text(),'last_name':dlg.last.text(),'email':dlg.email.text(),'password':dlg.password.text(),'position_id':dlg.position.currentData(),'role_name':dlg.role.currentData()});self.refresh_admin_page('staff')
        except Exception as e:message_error(self,'Не удалось изменить сотрудника',e)

    def toggle_staff(self):
        eid=selected(self.staff_table,'employee_id')
        if not eid:return
        try:self.service.toggle_staff_active(self.user,eid);self.refresh_admin_page('staff')
        except Exception as e:message_error(self,'Не удалось изменить статус сотрудника',e)

    def selected_payment(self):return selected(self.payments_table,'payment_id') if hasattr(self,'payments_table') else None

    def review_payment(self,approved):
        pid=self.selected_payment()
        if not pid:return
        try:self.service.confirm_payment(self.user,pid,approved,'Проверка администратором');self.refresh_admin_page('finance')
        except Exception as e:message_error(self,'Не удалось обработать платёж',e)

    def refund_payment(self):
        pid=self.selected_payment()
        if not pid:return
        row=next((r for r in self.service.admin_payments() if r['payment_id']==pid),None)
        if not row:return
        amount,ok=QInputDialog.getDouble(self,'Возврат','Сумма возврата, ₽:',float(row['amount']),0.01,float(row['amount']),2)
        if not ok:return
        reason,ok=QInputDialog.getText(self,'Возврат','Причина возврата:')
        if not ok:return
        try:self.service.process_refund(self.user,pid,amount,reason,approve=True);self.refresh_admin_page('finance')
        except Exception as e:message_error(self,'Не удалось оформить возврат',e)

    def review_refund(self,approve):
        rid=selected(self.refunds_table,'refund_id')
        if not rid:return
        try:self.service.process_refund_review(self.user,rid,approve);self.refresh_admin_page('finance')
        except Exception as e:message_error(self,'Не удалось обработать возврат',e)

    def refresh_admin_notifications(self):
        self.admin_notification_list.clear()
        rows=self.service.notifications(self.user)
        for r in rows:
            item=QListWidgetItem(('● ' if not r['is_read'] else '○ ')+f"{r['title']} · {r['message']} · {pretty(r['created_at'])}");item.setData(Qt.UserRole,r['notification_id']);self.admin_notification_list.addItem(item)

    def mark_admin_notification(self):
        items=self.admin_notification_list.selectedItems()
        if not items:return
        self.service.mark_notifications_read(self.user,[i.data(Qt.UserRole) for i in items]);self.refresh_admin_notifications()

    def refresh_admin_weather(self):
        latest=self.service.latest_weather()
        if latest:
            self.admin_weather_title.setText(f"{weather_condition(latest['weather_code'])} · {latest['temperature']} °C · {self.risk_title(latest['safety_level'])} · {pretty(latest['observed_at'])}")
        self.clear_layout(self.admin_weather_grid)
        if latest:
            for i,(title,value) in enumerate([('Ветер',f"{latest['wind_speed']} км/ч"),('Порывы',f"{latest['wind_gust']} км/ч"),('Осадки',f"{latest['precipitation']} мм"),('Облачность',f"{latest['cloud_cover']}%")]):
                self.admin_weather_grid.addWidget(MetricCard(title,value),0,i)
        rows=self.service.weather_history(48);samples=[x for x in reversed(rows) if x['is_forecast']][:24]
        self.admin_weather_canvas.figure.clear();axes=self.admin_weather_canvas.figure.subplots(1,2)
        if samples:
            times=[x['observed_at'].astimezone().strftime('%d.%m %H:%M') for x in samples]
            axes[0].plot(times,[x['temperature'] for x in samples],color='#e5a44e');axes[0].set_title('Температура, °C')
            axes[1].plot(times,[x['wind_speed'] for x in samples],label='Ветер');axes[1].plot(times,[x['wind_gust'] for x in samples],label='Порывы');axes[1].legend();axes[1].set_title('Ветер, км/ч')
            tick_step=max(1,len(times)//6);tick_positions=list(range(0,len(times),tick_step))
            for ax in axes:
                ax.set_xticks(tick_positions);ax.set_xticklabels([times[i] for i in tick_positions],rotation=0,ha='center');ax.grid(axis='y',alpha=.2)
        else:
            for ax in axes:ax.text(.5,.5,'Прогноз отсутствует',ha='center',va='center');ax.set_axis_off()
        self.admin_weather_canvas.figure.tight_layout(pad=1.5);self.admin_weather_canvas.draw()

    def refresh_analytics(self):
        try:
            start=self.analytics_from.date().toPython();end=self.analytics_to.date().toPython()
            if start>end:raise ValueError('Начало периода позже окончания.')
            data=self.service.analytics(start,end);fig=self.analytics_canvas.figure;fig.clear()
            columns=2 if self.width()>=1150 else 1;axes=list(fig.subplots(4,columns).flat)
            self.analytics_canvas.setMinimumHeight(1100 if columns==2 else 2400)
            rev=data['revenue'];ax=axes[0]
            if rev:
                ax.plot([pretty(x['month']) for x in rev],[float(x['revenue']) for x in rev],marker='o',label='Выручка')
                ax.plot([pretty(x['month']) for x in rev],[float(x['previous_revenue'] or 0) for x in rev],linestyle='--',label='Предыдущий месяц')
                ax.legend();ax.set_title('Выручка по месяцам, ₽');ax.tick_params(axis='x',rotation=35)
            else:ax.text(.5,.5,'Нет платежей за выбранный период',ha='center');ax.set_axis_off()
            monthly=data['bookings_monthly'];ax=axes[1]
            if monthly:ax.bar([pretty(x['month_date']) for x in monthly],[x['bookings'] for x in monthly],color='#2695a0');ax.set_title('Количество бронирований по месяцам');ax.tick_params(axis='x',rotation=35)
            else:ax.text(.5,.5,'Нет бронирований за выбранный период',ha='center');ax.set_axis_off()
            boats=data['boats'][:10];ax=axes[2]
            if boats:ax.barh([x['boat_name'] for x in reversed(boats)],[x['bookings'] for x in reversed(boats)],color='#2695a0');ax.set_title('Популярность яхт по числу заявок')
            else:ax.text(.5,.5,'Нет заявок',ha='center');ax.set_axis_off()
            types=data['types'];ax=axes[3]
            if types:ax.bar([x['name'] for x in types],[float(x['revenue'] or 0) for x in types],color='#d5a75e');ax.set_title('Выручка по типам яхт, ₽');ax.tick_params(axis='x',rotation=30)
            else:ax.text(.5,.5,'Нет выручки по типам яхт',ha='center');ax.set_axis_off()
            statuses=data['statuses'];ax=axes[4]
            if statuses:ax.pie([x['count'] for x in statuses],labels=[pretty(x['status_code']) for x in statuses],autopct='%1.0f%%',wedgeprops={'width':.42});ax.set_title('Распределение заявок по статусам')
            else:ax.text(.5,.5,'Нет заявок за выбранный период',ha='center');ax.set_axis_off()
            util=data['utilization'][:10];ax=axes[5]
            if util:ax.barh([x['boat_name'] for x in reversed(util)],[float(x['utilization_percent'] or 0) for x in reversed(util)],color='#58a89c');ax.set_title('Загрузка флота, %');ax.set_xlim(0,100)
            else:ax.text(.5,.5,'Нет данных о загрузке флота',ha='center');ax.set_axis_off()
            by_boat=data['revenue_by_boat'][:10];ax=axes[6]
            if by_boat:ax.barh([x['boat_name'] for x in reversed(by_boat)],[float(x['revenue'] or 0) for x in reversed(by_boat)],color='#d5a75e');ax.set_title('Выручка по яхтам, ₽')
            else:ax.text(.5,.5,'Нет выручки по яхтам',ha='center');ax.set_axis_off()
            cmp=data['comparison'];ax=axes[7]
            if cmp:
                ax.bar(['Выбранный период','Предыдущий период'],[float(cmp['current_revenue']),float(cmp['previous_revenue'])],color=['#2695a0','#9ab4c3']);ax.set_title('Сравнение выручки, ₽')
            else:ax.text(.5,.5,'Нет данных для сравнения',ha='center');ax.set_axis_off()
            self.analytics_canvas.draw()
            rows=data['boats'];self.analytics_table=update_table(self.analytics_table,rows,[('rank_no','Ранг'),('boat_name','Яхта'),('bookings','Заявок'),('revenue','Выручка'),('boat_id','ID')],hidden=('boat_id',))
        except Exception as e:message_error(self,'Не удалось построить аналитику',e)

    def export_analytics(self,kind):
        ext='xlsx' if kind=='xlsx' else 'pdf';path,_=QFileDialog.getSaveFileName(self,'Экспорт аналитики',f'yacht_club_analytics.{ext}','Excel (*.xlsx)' if ext=='xlsx' else 'PDF (*.pdf)')
        if not path:return
        try:
            start=self.analytics_from.date().toPython();end=self.analytics_to.date().toPython();data=self.service.analytics(start,end)
            if ext=='xlsx':
                from openpyxl import Workbook
                from openpyxl.styles import Font,PatternFill
                wb=Workbook();wb.remove(wb.active)
                for name,rows in [('Флот',data['boats']),('Выручка',data['revenue']),('Загрузка',data['utilization']),('Статусы',data['statuses']),('Типы яхт',data['types']),('Клиенты',data['clients']),('Погода',data['weather'])]:
                    ws=wb.create_sheet(name)
                    if rows:
                        keys=list(rows[0]);ws.append(keys)
                        for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='153E59')
                        for row in rows:ws.append([row.get(k) for k in keys])
                        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
                wb.save(path)
            else:
                from reportlab.lib.pagesizes import landscape,A4
                from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib import colors
                story=[Paragraph('Yacht Club Manager · Аналитика',getSampleStyleSheet()['Title']),Paragraph(f'Период: {start} — {end}',getSampleStyleSheet()['Normal']),Spacer(1,16)]
                rows=data['boats'];story.append(Paragraph('Рейтинг яхт',getSampleStyleSheet()['Heading2']))
                table=[['Ранг','Яхта','Бронирования','Выручка']]+[[str(r['rank_no']),str(r['boat_name']),str(r['bookings']),money(r['revenue'])] for r in rows]
                t=Table(table,repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#153e59')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#bdcbd3')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#eff5f7')])]))
                story.append(t);SimpleDocTemplate(path,pagesize=landscape(A4),title='Yacht Club Analytics').build(story)
            QMessageBox.information(self,'Экспорт готов',f'Файл сохранён:\n{path}')
        except Exception as e:message_error(self,'Не удалось экспортировать отчёт',e)

    def run_sql(self):
        if self.user.get('role_name')!='admin':QMessageBox.warning(self,'Недостаточно прав','SQL-каталог доступен только администратору.');return
        preset=self.sql_query.currentData()
        sql=self.sql_input.toPlainText().strip() if self.sql_manual.isChecked() else (preset[2] if preset else '')
        if not sql or not re.match(r'^(SELECT|WITH)\b',sql,re.IGNORECASE) or ';' in sql.rstrip(';'):
            QMessageBox.warning(self,'Безопасный режим','Введите один запрос SELECT или WITH без команд изменения данных.');return
        banned=r'\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|call|do|execute|pg_read_file|pg_write_file|pg_sleep|dblink|lo_import|lo_export)\b'
        if re.search(banned,sql,re.IGNORECASE):
            QMessageBox.warning(self,'Запрос заблокирован','В запросе обнаружена команда или функция, недоступная в режиме чтения.');return
        started=datetime.now()
        try:
            rows=self.db.readonly_query(sql);cols=list(rows[0]) if rows else []
            normalized=[{k:r[k] for k in cols} for r in rows]
            self.sql_result=update_table(self.sql_result,normalized,[(k,k) for k in cols]);self.sql_time.setText(f"Строк: {len(rows)} · { (datetime.now()-started).total_seconds():.3f} с")
            if not rows:self.sql_time.setText(f"Запрос выполнен: строк не найдено · { (datetime.now()-started).total_seconds():.3f} с")
        except Exception as e:message_error(self,'Ошибка запроса',e)

    def closeEvent(self,event):
        try:self.db.close()
        except Exception:pass
        super().closeEvent(event)


def main():
    app=QApplication(sys.argv);app.setApplicationName('Yacht Club Manager');app.setStyleSheet(APP_STYLE)
    configure_logging()
    settings=load_settings()
    splash=QDialog();splash.setWindowTitle('Запуск Yacht Club Manager');splash.setFixedSize(480,185);layout=QVBoxLayout(splash)
    title=QLabel('Подключение к Yacht Club Manager');title.setObjectName('Title');layout.addWidget(title)
    state=QLabel('Проверяем PostgreSQL. При необходимости запускаем контейнер Docker…');state.setWordWrap(True);layout.addWidget(state)
    progress=QProgressBar();progress.setRange(0,0);layout.addWidget(progress);splash.show()
    keep={'worker':None,'window':None,'db':None}

    def connect_database():
        worker=BootWorker(settings);keep['worker']=worker
        worker.finished_result.connect(on_ready);worker.start()

    def on_ready(ok,info):
        splash.close()
        if not ok:
            QMessageBox.critical(None,'База данных недоступна',info+'\n\nПроверьте, что Docker Desktop установлен и запущен. Данные контейнера хранятся в постоянном томе.')
            app.quit();return
        try:
            db=Db(settings);db.rows('SELECT 1');window=MainWindow(db,settings);keep.update({'db':db,'window':window});window.show()
        except Exception as e:
            QMessageBox.critical(None,'Не удалось открыть приложение',f"Подключение установлено, но Yacht Club Manager не смог подготовить рабочее окно.\n\n{e}");app.quit()

    QTimer.singleShot(0,connect_database)
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())

