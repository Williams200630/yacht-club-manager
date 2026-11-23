from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request,urlopen


WMO = {0:'Ясно',1:'Преимущественно ясно',2:'Переменная облачность',3:'Пасмурно',45:'Туман',48:'Изморозь',
 51:'Слабая морось',53:'Морось',55:'Сильная морось',61:'Небольшой дождь',63:'Дождь',65:'Сильный дождь',
 71:'Небольшой снег',73:'Снег',75:'Сильный снег',80:'Ливень',81:'Ливень',82:'Сильный ливень',
 95:'Гроза',96:'Гроза с градом',99:'Сильная гроза'}


def weather_condition(code):
    return WMO.get(int(code or 0),'Условия не определены')


def assess(wind,gust,rules):
    danger=[r['name'] for r in rules if
            (wind is not None and wind>=float(r['danger_wind_speed'])) or (gust is not None and gust>=float(r['danger_gust']))]
    attention=[r['name'] for r in rules if r['name'] not in danger and
            ((wind is not None and wind>=float(r['warning_wind_speed'])) or (gust is not None and gust>=float(r['warning_gust'])))]
    if danger:return 'danger','Опасно',f"Превышены ограничения типа судна: {', '.join(danger)}. Автоматически подтверждать выход нельзя."
    if attention:return 'caution','Ограничения',f"Требуется ручная проверка для типов: {', '.join(attention)}."
    return 'favorable','Благоприятно','Установленные ветровые пороги для флота не превышены. Проверяйте официальные морские предупреждения.'


def fetch_weather(latitude,longitude,rules):
    params=urlencode({
      'latitude':latitude,'longitude':longitude,'timezone':'auto','forecast_days':7,
      'current':'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility',
      'hourly':'temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m,weather_code,cloud_cover,visibility',
      'daily':'weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_sum'
    })
    req=Request('https://api.open-meteo.com/v1/forecast?'+params,headers={'User-Agent':'YachtClubManager/1.0'})
    with urlopen(req,timeout=12) as response: payload=json.loads(response.read().decode('utf-8'))
    current=payload.get('current',{});hourly=payload.get('hourly',{})
    wind=float(current.get('wind_speed_10m') or 0);gust=float(current.get('wind_gusts_10m') or 0)
    risk=assess(wind,gust,rules)
    def get_hour(i,key):
        items=hourly.get(key,[])
        return items[i] if i<len(items) else None
    records=[]
    for i,stamp in enumerate(hourly.get('time',[])[:168]):
        hwind=get_hour(i,'wind_speed_10m');hgust=get_hour(i,'wind_gusts_10m');hlvl=assess(hwind,hgust,rules)
        records.append({
          'observed_at':datetime.fromisoformat(stamp).astimezone(timezone.utc) if datetime.fromisoformat(stamp).tzinfo else datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc),
          'temperature':get_hour(i,'temperature_2m'),'wind_speed':hwind,'wind_gust':hgust,
          'precipitation':get_hour(i,'precipitation'),'precipitation_probability':get_hour(i,'precipitation_probability'),
          'cloud_cover':get_hour(i,'cloud_cover'),'visibility_km':(get_hour(i,'visibility')/1000 if get_hour(i,'visibility') is not None else None),
          'weather_code':get_hour(i,'weather_code'),'condition':weather_condition(get_hour(i,'weather_code')),
          'safety_level':hlvl[0],'latitude':latitude,'longitude':longitude,'is_forecast':True
        })
    current_row={
      'observed_at':datetime.fromisoformat(current['time']).astimezone(timezone.utc) if datetime.fromisoformat(current['time']).tzinfo else datetime.fromisoformat(current['time']).replace(tzinfo=timezone.utc),
      'temperature':current.get('temperature_2m'),'wind_speed':wind,'wind_direction':current.get('wind_direction_10m'),'wind_gust':gust,
      'precipitation':current.get('precipitation'),'precipitation_probability':None,'cloud_cover':current.get('cloud_cover'),
      'visibility_km':(current['visibility']/1000 if current.get('visibility') is not None else None),
      'weather_code':current.get('weather_code'),'condition':weather_condition(current.get('weather_code')),
      'safety_level':risk[0],'latitude':latitude,'longitude':longitude,'is_forecast':False
    }
    return {'current':current_row,'risk':risk,'hourly':records,'daily':payload.get('daily',{}),'hourly_raw':hourly}
