from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING

from .db import Db
from .security import hash_password, validate_credentials, validate_phone, verify_password


class YachtService:
    def __init__(self, db: Db):
        self.db = db

    def authenticate(self, email: str, password: str) -> dict:
        row = self.db.one(
            """SELECT u.user_id,u.email,u.password_hash,u.is_active,r.role_name,
                      c.client_id,c.first_name,c.last_name,e.employee_id
               FROM users u JOIN roles r USING(role_id)
               LEFT JOIN clients c USING(user_id) LEFT JOIN employees e USING(user_id)
               WHERE lower(u.email)=lower(%s)""", (email.strip(),)
        )
        if not row or not row["is_active"] or not verify_password(password,row["password_hash"]):
            raise ValueError("Неверный email или пароль.")
        self.db.execute("UPDATE users SET last_login_at=now() WHERE user_id=%s",(row["user_id"],),row["user_id"])
        row.pop("password_hash",None)
        return row

    def register_client(self, first,last,phone,email,password,confirm,birth_date=None):
        validate_credentials(email,password); validate_phone(phone)
        if password!=confirm: raise ValueError("Пароли не совпадают.")
        if not first.strip() or not last.strip(): raise ValueError("Укажите имя и фамилию.")
        try:
            with self.db.transaction() as tx:
                u=tx.one("INSERT INTO users(role_id,email,password_hash) VALUES((SELECT role_id FROM roles WHERE role_name='client'),%s,%s) RETURNING user_id,email",(email.strip().lower(),hash_password(password)))
                c=tx.one("INSERT INTO clients(user_id,first_name,last_name,phone,birth_date) VALUES(%s,%s,%s,%s,%s) RETURNING client_id,first_name,last_name",(u['user_id'],first.strip(),last.strip(),phone.strip(),birth_date))
                tx.execute("INSERT INTO notifications(user_id,title,message) VALUES(%s,'Профиль создан','Добро пожаловать в Yacht Club Manager.')",(u['user_id'],))
            return {**u,**c,"role_name":"client"}
        except Exception as exc:
            if getattr(exc,"sqlstate",None)=="23505": raise ValueError("Пользователь с таким email уже зарегистрирован.") from exc
            raise

    def catalog(self,search="",boat_type=None,manufacturer=None,capacity=0,cabins=0,max_price=None,sort="Рекомендуемые",start_at=None,end_at=None,passengers=1,port_id=None):
        clauses=["NOT b.is_archived"]; params=[]
        if search.strip():
            clauses.append("(b.name ILIKE %s OR b.model ILIKE %s OR m.name ILIKE %s)")
            like=f"%{search.strip()}%"; params.extend([like,like,like])
        if boat_type: clauses.append("bt.name=%s"); params.append(boat_type)
        if manufacturer: clauses.append("m.name=%s"); params.append(manufacturer)
        if capacity: clauses.append("b.capacity>=%s"); params.append(capacity)
        if cabins: clauses.append("b.cabin_count>=%s"); params.append(cabins)
        if max_price is not None: clauses.append("b.daily_rate<=%s"); params.append(max_price)
        if port_id:clauses.append("EXISTS(SELECT 1 FROM berths br JOIN piers p USING(pier_id) WHERE br.berth_id=b.current_berth_id AND p.port_id=%s)");params.append(port_id)
        if start_at and end_at:
            clauses.append("b.boat_id IN(SELECT boat_id FROM fn_get_available_boats(%s,%s,%s))"); params.extend([start_at,end_at,passengers])
        order={"Дешевле":"b.daily_rate ASC","Дороже":"b.daily_rate DESC","По названию":"b.name ASC","Вместимость":"b.capacity DESC","Популярные":"c.booking_count DESC"}.get(sort,"c.booking_count DESC,b.daily_rate ASC")
        return self.db.rows("SELECT c.*,m.name AS manufacturer_name FROM vw_boat_catalog c JOIN boats b USING(boat_id) JOIN boat_types bt USING(boat_type_id) JOIN manufacturers m USING(manufacturer_id) WHERE "+" AND ".join(clauses)+" ORDER BY "+order,params)

    def boat_detail(self,boat_id):
        boat=self.db.one("SELECT * FROM vw_boat_catalog WHERE boat_id=%s",(boat_id,))
        if not boat: raise ValueError("Яхта не найдена.")
        boat['images']=self.db.rows("SELECT * FROM boat_images WHERE boat_id=%s ORDER BY is_cover DESC,sort_order,image_id",(boat_id,))
        boat['amenities']=self.db.rows("SELECT a.name,a.description FROM boat_amenities ba JOIN amenities a USING(amenity_id) WHERE ba.boat_id=%s ORDER BY a.name",(boat_id,))
        boat['services']=self.db.rows("""SELECT DISTINCT s.service_id,s.name,s.description,s.price,s.pricing_unit FROM services s
          LEFT JOIN service_boat_types st USING(service_id) WHERE s.is_active AND (st.boat_type_id=(SELECT boat_type_id FROM boats WHERE boat_id=%s)
          OR NOT EXISTS(SELECT 1 FROM service_boat_types WHERE service_id=s.service_id)) ORDER BY s.name""",(boat_id,))
        return boat

    def quote(self,boat_id,client_id,start_at,end_at,passengers,service_ids=()):
        if end_at<=start_at: raise ValueError("Окончание аренды должно быть позже начала.")
        boat=self.db.one("SELECT hourly_rate,daily_rate,min_hours FROM boats WHERE boat_id=%s",(boat_id,))
        calc=self.db.one("SELECT * FROM fn_calculate_reservation_total(%s,%s,%s,%s,%s)",(boat_id,client_id,start_at,end_at,passengers))
        if not boat or not calc or not calc['capacity_ok']: raise ValueError("Яхта не подходит по вместимости.")
        hours=Decimal(str((end_at-start_at).total_seconds()))/Decimal(3600)
        if hours<Decimal(str(boat['min_hours'])): raise ValueError(f"Минимальная длительность аренды: {boat['min_hours']} ч.")
        days=int((hours/24).to_integral_value(rounding=ROUND_CEILING))
        base=Decimal(str(boat['daily_rate']))*days if hours>=24 else Decimal(str(boat['hourly_rate']))*hours
        discount=Decimal(str(calc['discount_percent']))
        services=self.db.rows("""SELECT DISTINCT s.service_id,s.name,s.price,s.pricing_unit FROM services s
          LEFT JOIN service_boat_types st USING(service_id) WHERE s.is_active AND s.service_id=ANY(%s)
          AND (st.boat_type_id=(SELECT boat_type_id FROM boats WHERE boat_id=%s) OR NOT EXISTS(SELECT 1 FROM service_boat_types WHERE service_id=s.service_id))""",(list(service_ids),boat_id)) if service_ids else []
        hours=Decimal(str((end_at-start_at).total_seconds()))/Decimal(3600)
        quantities=[max(1,int(hours.to_integral_value(rounding=ROUND_CEILING))) if 'час' in s['pricing_unit'].lower() else passengers if 'человек' in s['pricing_unit'].lower() else 1 for s in services]
        extras=sum((Decimal(str(s['price']))*q for s,q in zip(services,quantities)),Decimal(0))
        for s,q in zip(services,quantities):s['quantity']=q
        return {"base":base,"discount":discount,"services":services,"services_total":extras,"total":(base*(1-discount/100)+extras).quantize(Decimal('0.01'))}

    def create_reservation(self,user,boat_id,start_at,end_at,passengers,service_ids=(),comment=""):
        self.require_role(user,'client')
        try:
            with self.db.transaction(user['user_id']) as tx:
                boat=tx.one("SELECT b.boat_id,b.capacity,b.min_hours,b.hourly_rate,b.daily_rate,bs.code status FROM boats b JOIN boat_statuses bs ON bs.boat_status_id=b.status_id WHERE b.boat_id=%s AND NOT b.is_archived FOR UPDATE OF b",(boat_id,))
                if not boat: raise ValueError("Яхта недоступна.")
                if passengers>boat['capacity']: raise ValueError("Превышена вместимость яхты.")
                hours=Decimal(str((end_at-start_at).total_seconds()))/Decimal(3600)
                if end_at<=start_at or hours<Decimal(str(boat['min_hours'])): raise ValueError("Проверьте даты и минимальную длительность аренды.")
                if boat['status'] in ('unavailable','maintenance'): raise ValueError("Яхта временно недоступна.")
                maint=tx.one("SELECT maintenance_id FROM maintenance WHERE boat_id=%s AND status IN('planned','in_progress') AND daterange(start_at,COALESCE(end_at,DATE '9999-12-31'),'[]') && daterange(%s::date,%s::date,'[]') LIMIT 1",(boat_id,start_at,end_at))
                if maint: raise ValueError("Яхта проходит обслуживание в выбранный период.")
                conflict=tx.one("SELECT reservation_id FROM reservations WHERE boat_id=%s AND status_code IN('pending','confirmed','awaiting_payment','paid','active') AND tstzrange(start_at,end_at,'[)') && tstzrange(%s,%s,'[)') LIMIT 1",(boat_id,start_at,end_at))
                if conflict: raise ValueError("Период уже занят другой заявкой.")
                client=tx.one("SELECT client_id FROM clients WHERE user_id=%s AND membership_status='active'",(user['user_id'],))
                if not client: raise ValueError("Профиль клиента заблокирован.")
                calc=tx.one("SELECT * FROM fn_calculate_reservation_total(%s,%s,%s,%s,%s)",(boat_id,client['client_id'],start_at,end_at,passengers))
                days=int((hours/24).to_integral_value(rounding=ROUND_CEILING))
                base=Decimal(str(boat['daily_rate']))*days if hours>=24 else Decimal(str(boat['hourly_rate']))*hours
                discount=Decimal(str(calc['discount_percent']))
                svcs=tx.rows("""SELECT DISTINCT s.service_id,s.price,s.pricing_unit FROM services s LEFT JOIN service_boat_types st USING(service_id)
                  WHERE s.is_active AND s.service_id=ANY(%s) AND (st.boat_type_id=(SELECT boat_type_id FROM boats WHERE boat_id=%s)
                  OR NOT EXISTS(SELECT 1 FROM service_boat_types WHERE service_id=s.service_id))""",(list(service_ids),boat_id)) if service_ids else []
                quantities=[max(1,int(hours.to_integral_value(rounding=ROUND_CEILING))) if 'час' in s['pricing_unit'].lower() else passengers if 'человек' in s['pricing_unit'].lower() else 1 for s in svcs]
                total=(base*(1-discount/100)+sum((Decimal(str(s['price']))*q for s,q in zip(svcs,quantities)),Decimal(0))).quantize(Decimal('0.01'))
                home=tx.one("""SELECT COALESCE(
                    (SELECT p.port_id FROM berth_assignments ba JOIN berths br USING(berth_id)
                     JOIN piers p USING(pier_id) JOIN ports pt USING(port_id)
                     WHERE ba.boat_id=b.boat_id AND ba.start_at<=%s AND (ba.end_at IS NULL OR ba.end_at>%s) AND p.is_active AND pt.is_active
                     ORDER BY ba.start_at DESC LIMIT 1),
                    (SELECT p.port_id FROM berths br JOIN piers p USING(pier_id) JOIN ports pt USING(port_id)
                     WHERE br.berth_id=b.current_berth_id AND p.is_active AND pt.is_active)) port_id
                    FROM boats b WHERE b.boat_id=%s""",(start_at,start_at,boat_id))
                r=tx.one("""INSERT INTO reservations(client_id,boat_id,start_at,end_at,arrival_at,port_id,passenger_count,status_code,total_amount,discount_percent,customer_comment,quote_expires_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,now()+interval '24 hour') RETURNING reservation_id,total_amount""",(client['client_id'],boat_id,start_at,end_at,start_at,home.get('port_id') if home else None,passengers,total,discount,comment.strip()))
                for s,q in zip(svcs,quantities): tx.execute("INSERT INTO reservation_services(reservation_id,service_id,quantity,unit_price_snapshot) VALUES(%s,%s,%s,%s)",(r['reservation_id'],s['service_id'],q,s['price']))
                admins=tx.rows("SELECT user_id FROM users WHERE role_id=(SELECT role_id FROM roles WHERE role_name='admin') AND is_active")
                for a in admins: tx.execute("INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id) VALUES(%s,'Новая заявка',%s,'reservation','reservation',%s)",(a['user_id'],f"Новая заявка №{r['reservation_id']} ожидает решения.",r['reservation_id']))
                return r
        except Exception as exc:
            if getattr(exc,'sqlstate',None)=='23P01': raise ValueError("Период уже занят другой заявкой.") from exc
            raise

    def require_role(self,user,*roles):
        if not user or user.get('role_name') not in roles: raise PermissionError("Недостаточно прав для этой операции.")

    @staticmethod
    def status_title(code):
        return {'pending':'ожидает решения','confirmed':'подтверждена','awaiting_payment':'ожидает оплаты','paid':'оплачена','active':'активна','completed':'завершена','rejected':'отклонена','cancelled':'отменена','expired':'срок оплаты истёк'}.get(code,code)

    def change_reservation_status(self,user,reservation_id,status,note=""):
        self.require_role(user,'admin','manager')
        if status not in {'confirmed','rejected','awaiting_payment','cancelled','active','completed','expired'}: raise ValueError("Недопустимый статус.")
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one("SELECT r.*,c.user_id FROM reservations r JOIN clients c USING(client_id) WHERE reservation_id=%s FOR UPDATE",(reservation_id,))
            if not r: raise ValueError("Заявка не найдена.")
            allowed={'pending':{'confirmed','rejected','cancelled'},'confirmed':{'awaiting_payment','cancelled'},'awaiting_payment':{'cancelled','expired'},'paid':{'active','cancelled'},'active':{'completed'}}
            if status not in allowed.get(r['status_code'],set()): raise ValueError(f"Нельзя сменить статус «{r['status_code']}» на «{status}».")
            if status=='confirmed':
                risk=tx.one("""SELECT bt.name FROM boats b JOIN boat_types bt USING(boat_type_id) JOIN safety_rules sr USING(boat_type_id)
                  JOIN weather_observations w ON w.is_forecast AND w.observed_at BETWEEN %s AND %s
                  WHERE b.boat_id=%s AND (w.wind_speed>=sr.danger_wind_speed OR w.wind_gust>=sr.danger_gust) LIMIT 1""",(r['start_at'],r['end_at'],r['boat_id']))
                if risk:raise ValueError(f"Подтверждение заблокировано: прогноз превышает опасный порог типа «{risk['name']}».")
                port=tx.one("""SELECT COALESCE(hist.port_id,current_port.port_id) port_id,
                  COALESCE(hist.name,current_port.name) name,COALESCE(hist.address,current_port.address) address,
                  COALESCE(hist.city,current_port.city) city,COALESCE(hist.phone,current_port.phone) phone
                  FROM boats boat
                  LEFT JOIN LATERAL (SELECT pt.port_id,pt.name,pt.address,pt.city,pt.phone FROM berth_assignments ba
                    JOIN berths br USING(berth_id) JOIN piers pr USING(pier_id) JOIN ports pt USING(port_id)
                    WHERE ba.boat_id=boat.boat_id AND ba.start_at<=%s AND (ba.end_at IS NULL OR ba.end_at>%s) AND pr.is_active AND pt.is_active
                    ORDER BY ba.start_at DESC LIMIT 1) hist ON TRUE
                  LEFT JOIN berths cbr ON cbr.berth_id=boat.current_berth_id
                  LEFT JOIN piers cpr ON cpr.pier_id=cbr.pier_id AND cpr.is_active
                  LEFT JOIN ports current_port ON current_port.port_id=cpr.port_id AND current_port.is_active
                  WHERE boat.boat_id=%s""",(r['start_at'],r['start_at'],r['boat_id']))
                if not port or not port['port_id']:raise ValueError('У яхты нет активного порта на дату заявки. Сначала разместите яхту на месте стоянки в активном порту.')
                berth=tx.one("""SELECT br.berth_id,br.berth_number,pr.name pier_name FROM berths br JOIN piers pr USING(pier_id)
                  JOIN boats boat ON boat.boat_id=%s
                  WHERE pr.port_id=%s AND pr.is_active AND br.status='active' AND br.max_length>=boat.length AND br.max_width>=boat.width AND br.max_draft>=boat.draft
                    AND (NOT EXISTS(SELECT 1 FROM boats x WHERE x.current_berth_id=br.berth_id AND NOT x.is_archived) OR br.berth_id=boat.current_berth_id)
                    AND NOT EXISTS(SELECT 1 FROM reservations x WHERE x.pickup_berth_id=br.berth_id AND x.status_code IN('confirmed','awaiting_payment','paid','active') AND tstzrange(x.start_at,x.end_at,'[)') && tstzrange(%s,%s,'[)'))
                  ORDER BY (br.berth_id=boat.current_berth_id) DESC,br.berth_number LIMIT 1 FOR UPDATE OF br SKIP LOCKED""",(r['boat_id'],port['port_id'],r['start_at'],r['end_at']))
                tx.execute("UPDATE reservations SET port_id=%s,pickup_berth_id=%s,arrival_at=start_at WHERE reservation_id=%s",(port['port_id'],berth['berth_id'] if berth else None,reservation_id))
                place=f"Причал {berth['pier_name']}, место {berth['berth_number']}" if berth else 'Точное место стоянки будет уточнено дополнительно.'
                msg=f"Ваша заявка подтверждена! Ваша яхта будет ждать вас в порту {port['name']}. Адрес: {port['address'] or 'не указан'}{', '+port['city'] if port['city'] else ''}. {place} Прибытие: {r['start_at']:%d.%m.%Y %H:%M}. Контакт порта: {port['phone'] or 'не указан'}."
            else:msg=f"Заявка №{reservation_id}: {self.status_title(status)}. {note.strip()}"
            tx.execute("UPDATE reservations SET status_code=%s,manager_id=%s,cancellation_note=%s WHERE reservation_id=%s",(status,user.get('employee_id'),note.strip(),reservation_id))
            tx.execute("INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id) VALUES(%s,'Изменился статус заявки',%s,'reservation','reservation',%s)",(r['user_id'],msg,reservation_id))

    def cancel_reservation(self,user,reservation_id):
        self.require_role(user,'client')
        client=self.db.value("SELECT client_id FROM clients WHERE user_id=%s",(user['user_id'],))
        row=self.db.one("SELECT status_code FROM reservations WHERE reservation_id=%s AND client_id=%s",(reservation_id,client))
        if not row or row['status_code'] not in ('pending','confirmed','awaiting_payment'): raise ValueError("Эту заявку нельзя отменить самостоятельно.")
        self.db.execute("UPDATE reservations SET status_code='cancelled',cancellation_note='Отменено клиентом' WHERE reservation_id=%s",(reservation_id,),user['user_id'])

    def demo_payment(self,user,reservation_id,successful=True):
        self.require_role(user,'client')
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one("SELECT r.*,c.client_id FROM reservations r JOIN clients c USING(client_id) WHERE reservation_id=%s AND c.user_id=%s FOR UPDATE",(reservation_id,user['user_id']))
            if not r or r['status_code'] not in ('confirmed','awaiting_payment'): raise ValueError("Оплатить можно только подтверждённую заявку.")
            bal=tx.one("SELECT balance FROM vw_payment_summary WHERE reservation_id=%s",(reservation_id,))['balance']
            if bal<=0: raise ValueError("Заявка уже оплачена.")
            method=tx.one("SELECT payment_method_id FROM payment_methods WHERE name='Демо-оплата'")
            status='confirmed' if successful else 'declined'
            p=tx.one("""INSERT INTO payments(reservation_id,client_id,method_id,amount,status,confirmed_at,is_test,note)
              VALUES(%s,%s,%s,%s,%s,CASE WHEN %s='confirmed' THEN now() END,true,'Учебная имитация оплаты')
              RETURNING payment_id,status,amount""",(reservation_id,r['client_id'],method['payment_method_id'],bal,status,status))
            if successful:
                tx.execute("UPDATE reservations SET status_code='paid' WHERE reservation_id=%s",(reservation_id,))
                location=self._reservation_pickup_info(tx,reservation_id)
                if location.get('resolved_port_id'):tx.execute('UPDATE reservations SET port_id=COALESCE(port_id,%s),arrival_at=COALESCE(arrival_at,start_at) WHERE reservation_id=%s',(location['resolved_port_id'],reservation_id))
                p['pickup_message']=self._format_pickup_info(location)
                tx.execute("INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id) VALUES(%s,'Оплата прошла',%s,'payment','payment',%s)",(user['user_id'],f"Оплата по заявке №{reservation_id} принята. Квитанция готова. {p['pickup_message']}",p['payment_id']))
            return p

    @staticmethod
    def _reservation_pickup_info(tx,reservation_id):
        return tx.one("""SELECT r.reservation_id,r.start_at,r.port_id,r.pickup_berth_id,b.name boat_name,
          COALESCE(r.port_id,hist.port_id,current_port.port_id) resolved_port_id,
          COALESCE(saved.name,hist.name,current_port.name) port_name,
          COALESCE(saved.address,hist.address,current_port.address) port_address,
          COALESCE(saved.city,hist.city,current_port.city) port_city,
          COALESCE(saved.phone,hist.phone,current_port.phone) port_phone,
          COALESCE(saved.is_demonstration,FALSE) port_is_demonstration,
          pickup_pier.name pickup_pier_name,pickup_berth.berth_number pickup_berth_number
          FROM reservations r JOIN boats b USING(boat_id)
          LEFT JOIN ports saved ON saved.port_id=r.port_id
          LEFT JOIN LATERAL (SELECT pt.port_id,pt.name,pt.address,pt.city,pt.phone FROM berth_assignments ba
            JOIN berths br USING(berth_id) JOIN piers pr USING(pier_id) JOIN ports pt USING(port_id)
            WHERE ba.boat_id=r.boat_id AND ba.start_at<=r.start_at AND (ba.end_at IS NULL OR ba.end_at>r.start_at)
            ORDER BY ba.start_at DESC LIMIT 1) hist ON TRUE
          LEFT JOIN berths current_berth ON current_berth.berth_id=b.current_berth_id
          LEFT JOIN piers current_pier ON current_pier.pier_id=current_berth.pier_id
          LEFT JOIN ports current_port ON current_port.port_id=current_pier.port_id
          LEFT JOIN berths pickup_berth ON pickup_berth.berth_id=r.pickup_berth_id
          LEFT JOIN piers pickup_pier ON pickup_pier.pier_id=pickup_berth.pier_id
          WHERE r.reservation_id=%s""",(reservation_id,)) or {}

    @staticmethod
    def _format_pickup_info(row):
        if not row.get('port_name'):
            return 'Порт отправления пока не указан. Пожалуйста, свяжитесь с яхт-клубом для уточнения.'
        address=', '.join(x for x in (row.get('port_address'),row.get('port_city')) if x) or 'адрес не указан'
        place=(f"Причал {row['pickup_pier_name']}, место {row['pickup_berth_number']}" if row.get('pickup_pier_name') and row.get('pickup_berth_number') else 'Точное место стоянки будет уточнено дополнительно.')
        arrival=row.get('start_at')
        arrival_text=arrival.strftime('%d.%m.%Y %H:%M') if arrival else 'не указано'
        demo_note=' Это демонстрационная точка карты, а не подтверждённое место выдачи.' if row.get('port_is_demonstration') else ''
        return f"Яхта «{row.get('boat_name') or 'яхта'}» будет ждать вас в порту {row['port_name']}. Адрес: {address}. {place} Прибытие: {arrival_text}. Контакт порта: {row.get('port_phone') or 'не указан'}.{demo_note}"

    def request_transfer_payment(self,user,reservation_id,reference=""):
        self.require_role(user,'client')
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one("SELECT r.*,c.client_id FROM reservations r JOIN clients c USING(client_id) WHERE reservation_id=%s AND c.user_id=%s FOR UPDATE",(reservation_id,user['user_id']))
            if not r or r['status_code'] not in ('confirmed','awaiting_payment'): raise ValueError("Перевод можно указать только для подтверждённой заявки.")
            bal=tx.one("SELECT balance FROM vw_payment_summary WHERE reservation_id=%s",(reservation_id,))['balance']
            if bal<=0: raise ValueError("Заявка уже оплачена.")
            method=tx.one("SELECT payment_method_id FROM payment_methods WHERE name='Банковский перевод'")
            return tx.one("""INSERT INTO payments(reservation_id,client_id,method_id,amount,status,external_reference,note)
              VALUES(%s,%s,%s,%s,'pending_confirmation',%s,'Ожидает проверки перевода') RETURNING payment_id""",(reservation_id,r['client_id'],method['payment_method_id'],bal,reference.strip()))

    def confirm_payment(self,user,payment_id,approved=True,note=""):
        self.require_role(user,'admin','manager')
        with self.db.transaction(user['user_id']) as tx:
            p=tx.one("SELECT p.*,c.user_id FROM payments p JOIN clients c USING(client_id) WHERE payment_id=%s FOR UPDATE",(payment_id,))
            if not p or p['status']!='pending_confirmation': raise ValueError("Платёж не ожидает подтверждения.")
            status='confirmed' if approved else 'declined'
            tx.execute("UPDATE payments SET status=%s,confirmed_at=CASE WHEN %s='confirmed' THEN now() END,note=%s WHERE payment_id=%s",(status,status,note,payment_id))
            if approved:
                bal=tx.one("SELECT balance FROM vw_payment_summary WHERE reservation_id=%s",(p['reservation_id'],))['balance']
                if bal<=0: tx.execute("UPDATE reservations SET status_code='paid' WHERE reservation_id=%s",(p['reservation_id'],))
            tx.execute("INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id) VALUES(%s,'Проверка платежа',%s,'payment','payment',%s)",(p['user_id'],'Платёж подтверждён.' if approved else 'Платёж отклонён.',payment_id))

    def process_refund(self,user,payment_id,amount,reason,approve=True):
        self.require_role(user,'admin')
        if Decimal(str(amount))<=0 or not reason.strip(): raise ValueError("Укажите сумму и причину возврата.")
        with self.db.transaction(user['user_id']) as tx:
            p=tx.one("SELECT * FROM payments WHERE payment_id=%s FOR UPDATE",(payment_id,))
            if not p or p['status'] not in ('confirmed','partially_refunded'): raise ValueError("Для этого платежа нельзя оформить возврат.")
            already=tx.one("SELECT COALESCE(sum(amount),0) total FROM refunds WHERE payment_id=%s AND status='processed'",(payment_id,))['total']
            if Decimal(str(amount))>p['amount']-already: raise ValueError("Возврат превышает оставшуюся сумму.")
            status='processed' if approve else 'pending'
            rf=tx.one("INSERT INTO refunds(payment_id,amount,reason,status,processed_at,processed_by) VALUES(%s,%s,%s,%s,CASE WHEN %s='processed' THEN now() END,%s) RETURNING refund_id",(payment_id,amount,reason.strip(),status,status,user.get('employee_id')))
            if approve:
                total=already+Decimal(str(amount))
                tx.execute("UPDATE payments SET status=%s WHERE payment_id=%s",('refunded' if total>=p['amount'] else 'partially_refunded',payment_id))
            return rf

    def process_refund_review(self,user,refund_id,approve=True):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one("SELECT rf.*,p.amount payment_amount FROM refunds rf JOIN payments p USING(payment_id) WHERE refund_id=%s FOR UPDATE OF rf,p",(refund_id,))
            if not r or r['status']!='pending': raise ValueError("Возврат уже обработан.")
            status='processed' if approve else 'rejected'
            tx.execute("UPDATE refunds SET status=%s,processed_at=now(),processed_by=%s WHERE refund_id=%s",(status,user.get('employee_id'),refund_id))
            if approve:
                total=tx.one("SELECT COALESCE(sum(amount),0) total FROM refunds WHERE payment_id=%s AND status='processed'",(r['payment_id'],))['total']
                tx.execute("UPDATE payments SET status=%s WHERE payment_id=%s",('refunded' if total>=r['payment_amount'] else 'partially_refunded',r['payment_id']))

    def user_reservations(self,user):
        self.require_role(user,'client')
        return self.db.rows("""SELECT r.*,b.name boat_name,s.title status_title,ps.charged,ps.paid,ps.balance,
          pt.port_id resolved_port_id,pt.name port_name,pt.address port_address,pt.city port_city,pt.phone port_phone,br.berth_number pickup_berth_number,pr.name pickup_pier_name,
          (SELECT image_path FROM port_images WHERE port_id=pt.port_id ORDER BY is_cover DESC,image_id LIMIT 1) port_image,
          COALESCE((SELECT json_agg(json_build_object('name',sv.name,'quantity',rs.quantity,'price',rs.unit_price_snapshot)) FROM reservation_services rs JOIN services sv USING(service_id) WHERE rs.reservation_id=r.reservation_id),'[]') services
          FROM reservations r JOIN clients c USING(client_id) JOIN boats b USING(boat_id) JOIN reservation_statuses s ON s.code=r.status_code
          LEFT JOIN ports pt ON pt.port_id=COALESCE(r.port_id,
            (SELECT hist_pt.port_id FROM berth_assignments ba JOIN berths hist_br USING(berth_id) JOIN piers hist_pr USING(pier_id) JOIN ports hist_pt USING(port_id)
             WHERE ba.boat_id=r.boat_id AND ba.start_at<=r.start_at AND (ba.end_at IS NULL OR ba.end_at>r.start_at) ORDER BY ba.start_at DESC LIMIT 1),
            (SELECT cur_pt.port_id FROM berths cur_br JOIN piers cur_pr USING(pier_id) JOIN ports cur_pt USING(port_id) WHERE cur_br.berth_id=b.current_berth_id))
            LEFT JOIN berths br ON br.berth_id=r.pickup_berth_id LEFT JOIN piers pr USING(pier_id)
          LEFT JOIN vw_payment_summary ps USING(reservation_id) WHERE c.user_id=%s ORDER BY r.created_at DESC""",(user['user_id'],))

    def user_payments(self,user):
        return self.db.rows("""SELECT p.*,r.total_amount,b.name boat_name,rc.receipt_number,rc.file_path
          FROM payments p JOIN clients c USING(client_id) JOIN reservations r USING(reservation_id) JOIN boats b USING(boat_id)
          LEFT JOIN receipts rc USING(payment_id) WHERE c.user_id=%s ORDER BY p.created_at DESC""",(user['user_id'],))

    def receipts(self,user,reservation_id=None):
        sql="""SELECT rc.*,p.payment_id,p.amount,p.status,p.confirmed_at,p.is_test,r.reservation_id,r.start_at,r.end_at,r.total_amount,
          c.first_name,c.last_name,c.phone,u.email,b.name boat_name,pm.name method
          FROM receipts rc JOIN payments p USING(payment_id) JOIN reservations r USING(reservation_id) JOIN clients c ON c.client_id=r.client_id
          JOIN users u ON u.user_id=c.user_id JOIN boats b ON b.boat_id=r.boat_id JOIN payment_methods pm ON pm.payment_method_id=p.method_id WHERE c.user_id=%s"""
        params=[user['user_id']]
        if reservation_id: sql+=" AND r.reservation_id=%s";params.append(reservation_id)
        return self.db.rows(sql+" ORDER BY rc.issued_at DESC",params)

    def favorites(self,user):
        return self.db.rows("SELECT b.* FROM favorites f JOIN vw_boat_catalog b USING(boat_id) WHERE f.user_id=%s ORDER BY f.created_at DESC",(user['user_id'],))

    def toggle_favorite(self,user,boat_id):
        self.require_role(user,'client')
        exists=self.db.value("SELECT EXISTS(SELECT 1 FROM favorites WHERE user_id=%s AND boat_id=%s)",(user['user_id'],boat_id))
        if exists: self.db.execute("DELETE FROM favorites WHERE user_id=%s AND boat_id=%s",(user['user_id'],boat_id),user['user_id'])
        else: self.db.execute("INSERT INTO favorites(user_id,boat_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(user['user_id'],boat_id),user['user_id'])
        return not exists

    def add_review(self,user,reservation_id,rating,comment):
        self.require_role(user,'client')
        if not 1<=rating<=5: raise ValueError("Оценка должна быть от 1 до 5.")
        return self.db.execute("""INSERT INTO reviews(client_id,boat_id,reservation_id,rating,comment)
          SELECT c.client_id,r.boat_id,r.reservation_id,%s,%s FROM reservations r JOIN clients c USING(client_id) JOIN rentals x USING(reservation_id)
          WHERE r.reservation_id=%s AND c.user_id=%s AND r.status_code='completed' AND x.status='closed'""",(rating,comment.strip(),reservation_id,user['user_id']),user['user_id'])

    def notifications(self,user,unread_only=False):
        q="SELECT * FROM notifications WHERE user_id=%s"+(' AND NOT is_read' if unread_only else '')+" ORDER BY created_at DESC LIMIT 200"
        return self.db.rows(q,(user['user_id'],))

    def mark_notifications_read(self,user,ids=None):
        if ids: self.db.execute("UPDATE notifications SET is_read=true WHERE user_id=%s AND notification_id=ANY(%s)",(user['user_id'],list(ids)),user['user_id'])
        else: self.db.execute("UPDATE notifications SET is_read=true WHERE user_id=%s",(user['user_id'],),user['user_id'])

    def user_reservations(self,user):
        self.require_role(user,'client')
        return self.db.rows("""SELECT r.*,b.name boat_name,s.title status_title,ps.charged,ps.paid,ps.balance,
          pt.port_id resolved_port_id,pt.name port_name,pt.address port_address,pt.city port_city,pt.phone port_phone,br.berth_number pickup_berth_number,pr.name pickup_pier_name,
          (SELECT image_path FROM port_images WHERE port_id=pt.port_id ORDER BY is_cover DESC,image_id LIMIT 1) port_image,
          COALESCE((SELECT json_agg(json_build_object('name',sv.name,'quantity',rs.quantity,'price',rs.unit_price_snapshot)) FROM reservation_services rs JOIN services sv USING(service_id) WHERE rs.reservation_id=r.reservation_id),'[]') services
          FROM reservations r JOIN clients c USING(client_id) JOIN boats b USING(boat_id) JOIN reservation_statuses s ON s.code=r.status_code
          LEFT JOIN ports pt ON pt.port_id=COALESCE(r.port_id,
            (SELECT hist_pt.port_id FROM berth_assignments ba JOIN berths hist_br USING(berth_id) JOIN piers hist_pr USING(pier_id) JOIN ports hist_pt USING(port_id)
             WHERE ba.boat_id=r.boat_id AND ba.start_at<=r.start_at AND (ba.end_at IS NULL OR ba.end_at>r.start_at) ORDER BY ba.start_at DESC LIMIT 1),
            (SELECT cur_pt.port_id FROM berths cur_br JOIN piers cur_pr USING(pier_id) JOIN ports cur_pt USING(port_id) WHERE cur_br.berth_id=b.current_berth_id))
            LEFT JOIN berths br ON br.berth_id=r.pickup_berth_id LEFT JOIN piers pr USING(pier_id)
          LEFT JOIN vw_payment_summary ps USING(reservation_id) WHERE c.user_id=%s ORDER BY r.created_at DESC""",(user['user_id'],))

    def receipts(self,user,reservation_id=None):
        self.require_role(user,'client')
        sql="""SELECT rc.*,p.payment_id,p.amount,p.status,p.confirmed_at,p.is_test,r.reservation_id,r.start_at,r.end_at,r.total_amount,
          c.first_name,c.last_name,c.phone,u.email,b.name boat_name,pm.name method
          FROM receipts rc JOIN payments p USING(payment_id) JOIN reservations r USING(reservation_id) JOIN clients c ON c.client_id=r.client_id
          JOIN users u ON u.user_id=c.user_id JOIN boats b ON b.boat_id=r.boat_id JOIN payment_methods pm ON pm.payment_method_id=p.method_id WHERE c.user_id=%s"""
        params=[user['user_id']]
        if reservation_id: sql+=" AND r.reservation_id=%s";params.append(reservation_id)
        return self.db.rows(sql+" ORDER BY rc.issued_at DESC",params)

    def user_payments(self,user):
        self.require_role(user,'client')
        return self.db.rows("""SELECT p.*,r.total_amount,b.name boat_name,rc.receipt_number
          FROM payments p JOIN clients c USING(client_id) JOIN reservations r USING(reservation_id) JOIN boats b USING(boat_id)
          LEFT JOIN receipts rc USING(payment_id) WHERE c.user_id=%s ORDER BY p.created_at DESC""",(user['user_id'],))

    def toggle_favorite(self,user,boat_id):
        self.require_role(user,'client')
        exists=self.db.value("SELECT EXISTS(SELECT 1 FROM favorites WHERE user_id=%s AND boat_id=%s)",(user['user_id'],boat_id))
        if exists:self.db.execute("DELETE FROM favorites WHERE user_id=%s AND boat_id=%s",(user['user_id'],boat_id),user['user_id'])
        else:self.db.execute("INSERT INTO favorites(user_id,boat_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(user['user_id'],boat_id),user['user_id'])
        return not exists

    def favorites(self,user):
        self.require_role(user,'client')
        return self.db.rows("SELECT c.* FROM favorites f JOIN vw_boat_catalog c USING(boat_id) WHERE f.user_id=%s ORDER BY f.created_at DESC",(user['user_id'],))

    def notifications(self,user,unread_only=False):
        q="SELECT * FROM notifications WHERE user_id=%s"+(' AND NOT is_read' if unread_only else '')+" ORDER BY created_at DESC LIMIT 200"
        return self.db.rows(q,(user['user_id'],))

    def mark_notifications_read(self,user,ids=None):
        if ids:self.db.execute("UPDATE notifications SET is_read=true WHERE user_id=%s AND notification_id=ANY(%s)",(user['user_id'],list(ids)),user['user_id'])
        else:self.db.execute("UPDATE notifications SET is_read=true WHERE user_id=%s",(user['user_id'],),user['user_id'])

    def cancel_reservation(self,user,reservation_id):
        self.require_role(user,'client')
        client=self.db.value("SELECT client_id FROM clients WHERE user_id=%s",(user['user_id'],))
        row=self.db.one("SELECT status_code FROM reservations WHERE reservation_id=%s AND client_id=%s",(reservation_id,client))
        if not row or row['status_code'] not in ('pending','confirmed','awaiting_payment'):raise ValueError("Эту заявку нельзя отменить самостоятельно.")
        self.db.execute("UPDATE reservations SET status_code='cancelled',cancellation_note='Отменено клиентом' WHERE reservation_id=%s",(reservation_id,),user['user_id'])

    def add_review(self,user,reservation_id,rating,comment):
        self.require_role(user,'client')
        if not 1<=rating<=5:raise ValueError("Оценка должна быть от 1 до 5.")
        count=self.db.execute("""INSERT INTO reviews(client_id,boat_id,reservation_id,rating,comment)
          SELECT c.client_id,r.boat_id,r.reservation_id,%s,%s FROM reservations r JOIN clients c USING(client_id) JOIN rentals x USING(reservation_id)
          WHERE r.reservation_id=%s AND c.user_id=%s AND r.status_code='completed' AND x.status='closed'""",(rating,comment.strip(),reservation_id,user['user_id']),user['user_id'])
        if not count:raise ValueError("Оставить отзыв можно после завершённой аренды.")

    def admin_dashboard(self):
        return self.db.one("""SELECT
          COALESCE((SELECT sum(amount) FROM payments WHERE status IN('confirmed','partially_refunded') AND confirmed_at::date=CURRENT_DATE),0) revenue_today,
          COALESCE((SELECT sum(amount) FROM payments WHERE status IN('confirmed','partially_refunded') AND confirmed_at>=date_trunc('month',now())),0) revenue_month,
          (SELECT count(*) FROM reservations WHERE status_code='pending') new_requests,
          (SELECT count(*) FROM reservations WHERE status_code='awaiting_payment') awaiting_payment,
          (SELECT count(*) FROM rentals WHERE status='issued') active_rentals,
          (SELECT count(*) FROM vw_boat_catalog WHERE boat_id IN(SELECT boat_id FROM fn_get_available_boats(now(),now()+interval '1 day',1))) free_boats,
          (SELECT count(*) FROM maintenance WHERE status IN('planned','in_progress')) maintenance,
          (SELECT count(*) FROM vw_payment_summary WHERE balance>0) debt_orders""")

    def admin_alerts(self):
        return self.db.rows("""SELECT 'Заявка ожидает решения' title,'Заявка №'||r.reservation_id||' поступила от '||c.first_name||' '||c.last_name message,'reservation' entity,r.reservation_id id,r.created_at
         FROM reservations r JOIN clients c USING(client_id) WHERE r.status_code='pending'
         UNION ALL SELECT 'Платёж ожидает проверки','Платёж №'||p.payment_id||' по заявке №'||p.reservation_id,'payment',p.payment_id,p.created_at FROM payments p WHERE p.status='pending_confirmation'
         UNION ALL SELECT 'Осмотр просрочен',b.name||': срок следующего осмотра прошёл','maintenance',m.maintenance_id,m.start_at::timestamptz FROM maintenance m JOIN boats b USING(boat_id) WHERE m.next_inspection_date<CURRENT_DATE AND m.status<>'cancelled'
         UNION ALL SELECT 'Скоро выдача',b.name||' · заявка №'||r.reservation_id,'reservation',r.reservation_id,r.start_at FROM reservations r JOIN boats b USING(boat_id) WHERE r.status_code='paid' AND r.start_at BETWEEN now() AND now()+interval '24 hour'
         UNION ALL SELECT 'Скоро возврат',b.name||' · заявка №'||r.reservation_id,'reservation',r.reservation_id,r.end_at FROM reservations r JOIN boats b USING(boat_id) WHERE r.status_code='active' AND r.end_at BETWEEN now() AND now()+interval '24 hour'
         UNION ALL SELECT DISTINCT 'Погодное ограничение',b.name||' · заявка №'||r.reservation_id,'reservation',r.reservation_id,w.observed_at FROM weather_observations w JOIN reservations r ON w.observed_at BETWEEN r.start_at AND r.end_at JOIN boats b USING(boat_id) JOIN safety_rules sr USING(boat_type_id) WHERE w.is_forecast AND w.wind_speed>=sr.danger_wind_speed AND r.status_code IN('pending','confirmed','awaiting_payment','paid')
         ORDER BY created_at DESC LIMIT 100""")

    def admin_applications(self,status=None):
        q="""SELECT r.reservation_id,c.first_name||' '||c.last_name client_name,u.email,c.phone,b.name boat_name,r.start_at,r.end_at,r.passenger_count,r.total_amount,r.status_code,rs.title status_title,r.created_at,r.customer_comment,
         pt.name port_name,pt.address port_address,pr.name pickup_pier_name,br.berth_number pickup_berth_number,
         COALESCE(v.paid,0) paid,COALESCE(v.balance,r.total_amount) balance
         FROM reservations r JOIN clients c USING(client_id) JOIN users u USING(user_id) JOIN boats b USING(boat_id)
         JOIN reservation_statuses rs ON rs.code=r.status_code LEFT JOIN ports pt USING(port_id)
         LEFT JOIN berths br ON br.berth_id=r.pickup_berth_id LEFT JOIN piers pr ON pr.pier_id=br.pier_id
         LEFT JOIN vw_payment_summary v USING(reservation_id)"""
        params=[]
        if status and status!="Все":q+=" WHERE r.status_code=%s";params.append(status)
        return self.db.rows(q+" ORDER BY r.created_at DESC LIMIT 500",params)

    def admin_payments(self):
        return self.db.rows("""SELECT p.payment_id,p.reservation_id,c.first_name||' '||c.last_name client_name,b.name boat_name,
         pm.name method,p.amount,p.status,p.created_at,p.confirmed_at,p.external_reference,p.is_test
         FROM payments p JOIN clients c USING(client_id) JOIN reservations r USING(reservation_id) JOIN boats b USING(boat_id)
         JOIN payment_methods pm ON pm.payment_method_id=p.method_id ORDER BY p.created_at DESC LIMIT 500""")

    def confirm_payment(self,user,payment_id,approved=True,note=""):
        self.require_role(user,'admin','manager')
        with self.db.transaction(user['user_id']) as tx:
            p=tx.one("SELECT p.*,c.user_id FROM payments p JOIN clients c USING(client_id) WHERE payment_id=%s FOR UPDATE",(payment_id,))
            if not p or p['status']!='pending_confirmation':raise ValueError("Платёж не ожидает подтверждения.")
            status='confirmed' if approved else 'declined'
            tx.execute("UPDATE payments SET status=%s,confirmed_at=CASE WHEN %s='confirmed' THEN now() END,note=%s WHERE payment_id=%s",(status,status,note,payment_id))
            if approved:
                balance=tx.one("SELECT balance FROM vw_payment_summary WHERE reservation_id=%s",(p['reservation_id'],))['balance']
                if balance<=0:
                    tx.execute("UPDATE reservations SET status_code='paid' WHERE reservation_id=%s",(p['reservation_id'],))
                    location=self._reservation_pickup_info(tx,p['reservation_id'])
                    if location.get('resolved_port_id'):tx.execute('UPDATE reservations SET port_id=COALESCE(port_id,%s),arrival_at=COALESCE(arrival_at,start_at) WHERE reservation_id=%s',(location['resolved_port_id'],p['reservation_id']))
                    message='Платёж подтверждён. '+self._format_pickup_info(location)
                else:message='Платёж подтверждён, но по заявке ещё остаётся задолженность.'
            else:message='Платёж отклонён.'
            tx.execute("INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id) VALUES(%s,'Проверка платежа',%s,'payment','payment',%s)",(p['user_id'],message,payment_id))

    def request_transfer_payment(self,user,reservation_id,reference=""):
        self.require_role(user,'client')
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one("SELECT r.*,c.client_id FROM reservations r JOIN clients c USING(client_id) WHERE reservation_id=%s AND c.user_id=%s FOR UPDATE",(reservation_id,user['user_id']))
            if not r or r['status_code'] not in ('confirmed','awaiting_payment'):raise ValueError("Перевод можно указать только для подтверждённой заявки.")
            balance=tx.one("SELECT balance FROM vw_payment_summary WHERE reservation_id=%s",(reservation_id,))['balance']
            if balance<=0:raise ValueError("Заявка уже оплачена.")
            method=tx.one("SELECT payment_method_id FROM payment_methods WHERE name='Банковский перевод'")
            p=tx.one("INSERT INTO payments(reservation_id,client_id,method_id,amount,status,external_reference,note) VALUES(%s,%s,%s,%s,'pending_confirmation',%s,'Ожидает проверки перевода') RETURNING payment_id",(reservation_id,r['client_id'],method['payment_method_id'],balance,reference.strip()))
            tx.execute("UPDATE reservations SET status_code='awaiting_payment' WHERE reservation_id=%s AND status_code='confirmed'",(reservation_id,))
            admins=tx.rows("SELECT user_id FROM users WHERE role_id=(SELECT role_id FROM roles WHERE role_name='admin') AND is_active")
            for admin in admins:tx.execute("INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id) VALUES(%s,'Перевод требует проверки',%s,'payment','payment',%s)",(admin['user_id'],f"Платёж №{p['payment_id']} ожидает подтверждения.",p['payment_id']))
            return p

    def process_refund(self,user,payment_id,amount,reason,approve=True):
        self.require_role(user,'admin')
        if Decimal(str(amount))<=0 or not reason.strip():raise ValueError("Укажите сумму и причину возврата.")
        with self.db.transaction(user['user_id']) as tx:
            p=tx.one("SELECT * FROM payments WHERE payment_id=%s FOR UPDATE",(payment_id,))
            if not p or p['status'] not in ('confirmed','partially_refunded'):raise ValueError("Для платежа нельзя оформить возврат.")
            already=tx.one("SELECT COALESCE(sum(amount),0) total FROM refunds WHERE payment_id=%s AND status='processed'",(payment_id,))['total']
            if Decimal(str(amount))>p['amount']-already:raise ValueError("Возврат превышает оставшуюся сумму платежа.")
            state='processed' if approve else 'pending'
            rf=tx.one("INSERT INTO refunds(payment_id,amount,reason,status,processed_at,processed_by) VALUES(%s,%s,%s,%s,CASE WHEN %s='processed' THEN now() END,%s) RETURNING refund_id",(payment_id,amount,reason.strip(),state,state,user.get('employee_id')))
            if approve:tx.execute("UPDATE payments SET status=%s WHERE payment_id=%s",('refunded' if already+Decimal(str(amount))>=p['amount'] else 'partially_refunded',payment_id))
            return rf

    def process_refund_review(self,user,refund_id,approve=True):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one("SELECT rf.*,p.amount payment_amount FROM refunds rf JOIN payments p USING(payment_id) WHERE refund_id=%s FOR UPDATE OF rf,p",(refund_id,))
            if not r or r['status']!='pending':raise ValueError("Возврат уже обработан.")
            state='processed' if approve else 'rejected'
            tx.execute("UPDATE refunds SET status=%s,processed_at=now(),processed_by=%s WHERE refund_id=%s",(state,user.get('employee_id'),refund_id))
            if approve:
                total=tx.one("SELECT COALESCE(sum(amount),0) total FROM refunds WHERE payment_id=%s AND status='processed'",(r['payment_id'],))['total']
                tx.execute("UPDATE payments SET status=%s WHERE payment_id=%s",('refunded' if total>=r['payment_amount'] else 'partially_refunded',r['payment_id']))

    def user_client_profile(self,user):
        self.require_role(user,'client')
        return self.db.one("""SELECT c.*,u.email,mt.name membership,mt.discount_percent,ms.end_date membership_end
          FROM clients c JOIN users u USING(user_id) LEFT JOIN LATERAL(SELECT membership_type_id,end_date FROM memberships WHERE client_id=c.client_id AND status='active' ORDER BY end_date DESC LIMIT 1) ms ON TRUE
          LEFT JOIN membership_types mt USING(membership_type_id) WHERE c.user_id=%s""",(user['user_id'],))

    def update_client_profile(self,user,first,last,phone,birth_date):
        self.require_role(user,'client');validate_phone(phone)
        self.db.execute("UPDATE clients SET first_name=%s,last_name=%s,phone=%s,birth_date=%s WHERE user_id=%s",(first.strip(),last.strip(),phone.strip(),birth_date,user['user_id']),user['user_id'])

    def change_password(self,user,current,new,confirm):
        if new!=confirm:raise ValueError("Пароли не совпадают.")
        if len(new)<10:raise ValueError("Новый пароль должен быть не короче 10 символов.")
        row=self.db.one("SELECT password_hash FROM users WHERE user_id=%s",(user['user_id'],))
        from .security import verify_password,hash_password
        if not row or not verify_password(current,row['password_hash']):raise ValueError("Текущий пароль неверен.")
        self.db.execute("UPDATE users SET password_hash=%s WHERE user_id=%s",(hash_password(new),user['user_id']),user['user_id'])

    def admin_clients(self,search=""):
        like=f"%{search}%"
        return self.db.rows("""SELECT c.client_id,c.first_name,c.last_name,c.phone,u.email,c.membership_status,mt.name membership,ms.end_date,
          COUNT(DISTINCT r.reservation_id) reservation_count,COALESCE(sumv.balance,0) balance,u.is_active,u.user_id
          FROM clients c JOIN users u USING(user_id)
          LEFT JOIN LATERAL(SELECT membership_type_id,end_date FROM memberships WHERE client_id=c.client_id AND status='active' ORDER BY end_date DESC LIMIT 1) ms ON TRUE
          LEFT JOIN membership_types mt USING(membership_type_id) LEFT JOIN reservations r USING(client_id)
          LEFT JOIN LATERAL(SELECT COALESCE(SUM(balance),0) balance FROM vw_payment_summary WHERE client_id=c.client_id) sumv ON TRUE
          WHERE (%s='' OR c.first_name ILIKE %s OR c.last_name ILIKE %s OR c.phone ILIKE %s OR u.email ILIKE %s)
          GROUP BY c.client_id,u.user_id,mt.name,ms.end_date,sumv.balance ORDER BY c.last_name,c.first_name""",(search,like,like,like,like))

    def update_client_profile(self,user,client_id,first_name,last_name,phone,email):
        self.require_role(user,'admin','manager');validate_phone(phone)
        if not first_name.strip() or not last_name.strip() or '@' not in email:raise ValueError('Проверьте имя, фамилию и email клиента.')
        try:
            with self.db.transaction(user['user_id']) as tx:
                row=tx.one('SELECT user_id FROM clients WHERE client_id=%s FOR UPDATE',(client_id,))
                if not row:raise ValueError('Клиент не найден.')
                tx.execute('UPDATE users SET email=%s WHERE user_id=%s',(email.strip().lower(),row['user_id']))
                tx.execute('UPDATE clients SET first_name=%s,last_name=%s,phone=%s WHERE client_id=%s',(first_name.strip(),last_name.strip(),phone.strip(),client_id))
        except Exception as exc:
            if getattr(exc,'sqlstate',None)=='23505':raise ValueError('Email уже используется другой учётной записью.') from exc
            raise

    def set_client_blocked(self,user,client_id,blocked,reason=""):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            row=tx.one("SELECT user_id FROM clients WHERE client_id=%s FOR UPDATE",(client_id,))
            if not row:raise ValueError("Клиент не найден.")
            tx.execute("UPDATE clients SET membership_status=%s,block_reason=%s WHERE client_id=%s",('blocked' if blocked else 'active',reason if blocked else None,client_id))
            tx.execute("UPDATE users SET is_active=%s WHERE user_id=%s",(not blocked,row['user_id']))

    def set_membership(self,user,client_id,membership_type_id,end_date):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            if not tx.one("SELECT client_id FROM clients WHERE client_id=%s FOR UPDATE",(client_id,)):raise ValueError("Клиент не найден.")
            tx.execute("UPDATE memberships SET status='expired',end_date=LEAST(end_date,CURRENT_DATE) WHERE client_id=%s AND status='active'",(client_id,))
            tx.execute("INSERT INTO memberships(client_id,membership_type_id,start_date,end_date,status) VALUES(%s,%s,CURRENT_DATE,%s,'active')",(client_id,membership_type_id,end_date))

    def admin_staff(self):
        return self.db.rows("""SELECT e.employee_id,e.position_id,u.email,e.first_name,e.last_name,p.position_name,r.role_name,e.hire_date,e.is_active,u.is_active AS account_active
          FROM employees e JOIN users u USING(user_id) JOIN roles r USING(role_id)
          LEFT JOIN positions p USING(position_id)
          ORDER BY e.is_active DESC,u.email""")

    def create_staff(self,user,first,last,email,password,position_id,role_name='manager'):
        self.require_role(user,'admin');validate_credentials(email,password)
        if role_name not in ('admin','manager'):raise ValueError("Сотруднику можно назначить только рабочую роль.")
        if not first.strip() or not last.strip():raise ValueError("Укажите имя и фамилию сотрудника.")
        try:
            with self.db.transaction(user['user_id']) as tx:
                u=tx.one("INSERT INTO users(role_id,email,password_hash) VALUES((SELECT role_id FROM roles WHERE role_name=%s),%s,%s) RETURNING user_id",(role_name,email.strip().lower(),hash_password(password)))
                tx.execute("INSERT INTO employees(user_id,position_id,first_name,last_name) VALUES(%s,%s,%s,%s)",(u['user_id'],position_id,first.strip(),last.strip()))
                tx.execute("INSERT INTO audit_log(user_id,action,entity_type,details) VALUES(%s,'create','employee',jsonb_build_object('email',%s,'role',%s))",(user['user_id'],email.strip().lower(),role_name))
        except Exception as exc:
            if getattr(exc,'sqlstate',None)=='23505':raise ValueError("Учетная запись с таким email уже существует.") from exc
            raise

    def update_staff(self,user,employee_id,data):
        self.require_role(user,'admin')
        if data.get('role_name') not in ('admin','manager'):raise ValueError('Недопустимая роль сотрудника.')
        email=str(data.get('email','')).strip().lower()
        if data.get('password'):validate_credentials(email,data['password'])
        else:
            if '@' not in email:raise ValueError('Укажите корректный email.')
        if not str(data.get('first_name','')).strip() or not str(data.get('last_name','')).strip():raise ValueError('Укажите имя и фамилию.')
        try:
            with self.db.transaction(user['user_id']) as tx:
                row=tx.one('SELECT user_id FROM employees WHERE employee_id=%s FOR UPDATE',(employee_id,))
                if not row:raise ValueError('Сотрудник не найден.')
                tx.execute('UPDATE users SET email=%s,role_id=(SELECT role_id FROM roles WHERE role_name=%s) WHERE user_id=%s',(email,data['role_name'],row['user_id']))
                if data.get('password'):tx.execute('UPDATE users SET password_hash=%s WHERE user_id=%s',(hash_password(data['password']),row['user_id']))
                tx.execute('UPDATE employees SET first_name=%s,last_name=%s,position_id=%s WHERE employee_id=%s',(data['first_name'].strip(),data['last_name'].strip(),data.get('position_id'),employee_id))
        except Exception as exc:
            if getattr(exc,'sqlstate',None)=='23505':raise ValueError('Учетная запись с таким email уже существует.') from exc
            raise

    def toggle_staff_active(self,user,employee_id):
        self.require_role(user,'admin')
        if employee_id==user.get('employee_id'):raise ValueError("Нельзя отключить собственную учётную запись.")
        with self.db.transaction(user['user_id']) as tx:
            row=tx.one("SELECT user_id,is_active FROM employees WHERE employee_id=%s FOR UPDATE",(employee_id,))
            if not row:raise ValueError("Сотрудник не найден.")
            tx.execute("UPDATE employees SET is_active=NOT is_active WHERE employee_id=%s",(employee_id,))
            tx.execute("UPDATE users SET is_active=NOT is_active WHERE user_id=%s",(row['user_id'],))

    def admin_boats(self,search=""):
        like=f"%{search}%"
        return self.db.rows("""SELECT b.*,bt.name boat_type,m.name manufacturer,bs.name status_name
          FROM boats b JOIN boat_types bt USING(boat_type_id) JOIN manufacturers m USING(manufacturer_id) JOIN boat_statuses bs ON bs.boat_status_id=b.status_id
          WHERE %s='' OR b.name ILIKE %s OR b.model ILIKE %s OR m.name ILIKE %s ORDER BY b.is_archived,b.name""",(search,like,like,like))

    def save_boat(self,user,data,boat_id=None):
        self.require_role(user,'admin')
        keys=('name','model','boat_type_id','manufacturer_id','status_id','production_year','length','width','draft','capacity','cabin_count','bathroom_count','engine_power','hourly_rate','daily_rate','min_hours','deposit_amount','description','equipment')
        vals=tuple(data.get(k) for k in keys)
        with self.db.transaction(user['user_id']) as tx:
            old=tx.one('SELECT current_berth_id FROM boats WHERE boat_id=%s FOR UPDATE',(boat_id,)) if boat_id else None
            if boat_id:
                tx.execute("UPDATE boats SET "+','.join(k+'=%s' for k in keys)+" WHERE boat_id=%s",vals+(boat_id,))
                saved_id=boat_id
            else:
                saved=tx.one("INSERT INTO boats("+','.join(keys)+",current_berth_id) VALUES("+','.join(['%s']*len(keys))+",NULL) RETURNING boat_id",vals)
                saved_id=saved['boat_id']
            new_berth=data.get('current_berth_id')
            if not old or old['current_berth_id']!=new_berth:
                if new_berth:
                    berth=tx.one("""SELECT br.berth_id FROM berths br JOIN piers p USING(pier_id) JOIN ports pt USING(port_id)
                      JOIN boats b ON b.boat_id=%s WHERE br.berth_id=%s AND br.status='active' AND p.is_active AND pt.is_active
                        AND br.max_length>=b.length AND br.max_width>=b.width AND br.max_draft>=b.draft FOR UPDATE OF br""",(saved_id,new_berth))
                    if not berth:raise ValueError('Место не подходит по габаритам яхты или недоступно.')
                    if tx.one('SELECT boat_id FROM boats WHERE current_berth_id=%s AND boat_id<>%s AND NOT is_archived',(new_berth,saved_id)):raise ValueError('Место уже занято другой яхтой.')
                    if tx.one("SELECT reservation_id FROM reservations WHERE pickup_berth_id=%s AND status_code IN('confirmed','awaiting_payment','paid','active') AND end_at>now() LIMIT 1",(new_berth,)):raise ValueError('Место зарезервировано под отправление по другой заявке.')
                tx.execute('UPDATE berth_assignments SET end_at=now() WHERE boat_id=%s AND end_at IS NULL',(saved_id,))
                tx.execute('UPDATE boats SET current_berth_id=%s WHERE boat_id=%s',(new_berth,saved_id))
                if new_berth:tx.execute('INSERT INTO berth_assignments(boat_id,berth_id,start_at,assigned_by) VALUES(%s,%s,now(),%s)',(saved_id,new_berth,user.get('employee_id')))
            tx.execute('DELETE FROM boat_amenities WHERE boat_id=%s',(saved_id,))
            for amenity_id in data.get('amenity_ids',[]):
                tx.execute('INSERT INTO boat_amenities(boat_id,amenity_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(saved_id,amenity_id))
        return saved_id

    def set_boat_cover(self,user,image_id):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            row=tx.one('SELECT boat_id FROM boat_images WHERE image_id=%s FOR UPDATE',(image_id,))
            if not row:raise ValueError('Изображение не найдено.')
            tx.execute('UPDATE boat_images SET is_cover=false WHERE boat_id=%s',(row['boat_id'],))
            tx.execute('UPDATE boat_images SET is_cover=true WHERE image_id=%s',(image_id,))

    def delete_boat_image(self,user,image_id):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            row=tx.one('SELECT boat_id,is_cover FROM boat_images WHERE image_id=%s FOR UPDATE',(image_id,))
            if not row:raise ValueError('Изображение не найдено.')
            tx.execute('DELETE FROM boat_images WHERE image_id=%s',(image_id,))
            if row['is_cover']:
                next_image=tx.one('SELECT image_id FROM boat_images WHERE boat_id=%s ORDER BY sort_order,image_id LIMIT 1',(row['boat_id'],))
                if next_image:tx.execute('UPDATE boat_images SET is_cover=true WHERE image_id=%s',(next_image['image_id'],))

    def archive_boat(self,user,boat_id):
        self.require_role(user,'admin');self.db.execute("UPDATE boats SET is_archived=true WHERE boat_id=%s",(boat_id,),user['user_id'])

    def admin_services(self):
        return self.db.rows("SELECT * FROM services ORDER BY is_active DESC,name")

    def save_service(self,user,data,service_id=None):
        self.require_role(user,'admin')
        if service_id:self.db.execute("UPDATE services SET name=%s,description=%s,price=%s,pricing_unit=%s,is_active=%s WHERE service_id=%s",(data['name'],data['description'],data['price'],data['pricing_unit'],data['is_active'],service_id),user['user_id'])
        else:self.db.execute("INSERT INTO services(name,description,price,pricing_unit,is_active) VALUES(%s,%s,%s,%s,%s)",(data['name'],data['description'],data['price'],data['pricing_unit'],data['is_active']),user['user_id'])

    def admin_maintenance(self):
        return self.db.rows("SELECT m.*,b.name boat_name,t.name type_name,u.email employee_email FROM maintenance m JOIN boats b USING(boat_id) JOIN maintenance_types t ON t.maintenance_type_id=m.type_id LEFT JOIN employees e USING(employee_id) LEFT JOIN users u USING(user_id) ORDER BY start_at DESC")

    def save_maintenance(self,user,data,maintenance_id=None):
        self.require_role(user,'admin','manager')
        values=(data['boat_id'],data['type_id'],user.get('employee_id'),data['start_at'],data['end_at'],data['description'],data.get('work_performed',''),data['cost'],data['status'],data['next_inspection_date'])
        if maintenance_id:
            self.db.execute('UPDATE maintenance SET boat_id=%s,type_id=%s,employee_id=%s,start_at=%s,end_at=%s,description=%s,work_performed=%s,cost=%s,status=%s,next_inspection_date=%s WHERE maintenance_id=%s',values+(maintenance_id,),user['user_id'])
        else:
            self.db.execute("INSERT INTO maintenance(boat_id,type_id,employee_id,start_at,end_at,description,work_performed,cost,status,next_inspection_date) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",values,user['user_id'])

    def assign_berth(self,user,boat_id,berth_id):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            boat=tx.one("SELECT boat_id,length,width,draft FROM boats WHERE boat_id=%s AND NOT is_archived FOR UPDATE",(boat_id,))
            berth=tx.one("SELECT br.*,p.port_id FROM berths br JOIN piers p USING(pier_id) JOIN ports pt USING(port_id) WHERE br.berth_id=%s AND br.status='active' AND p.is_active AND pt.is_active FOR UPDATE OF br",(berth_id,))
            if not boat or not berth:raise ValueError("Яхта или место не найдены.")
            if boat['length']>berth['max_length'] or boat['width']>berth['max_width'] or boat['draft']>berth['max_draft']:raise ValueError("Габариты яхты превышают допустимые параметры места.")
            if tx.one("SELECT boat_id FROM boats WHERE current_berth_id=%s AND boat_id<>%s AND NOT is_archived",(berth_id,boat_id)):raise ValueError("Место уже занято.")
            if tx.one("SELECT reservation_id FROM reservations WHERE pickup_berth_id=%s AND status_code IN('confirmed','awaiting_payment','paid','active') AND end_at>now() LIMIT 1",(berth_id,)):raise ValueError("Место зарезервировано под отправление по другой заявке.")
            tx.execute("UPDATE berth_assignments SET end_at=now() WHERE boat_id=%s AND end_at IS NULL",(boat_id,))
            tx.execute("INSERT INTO berth_assignments(boat_id,berth_id,start_at,assigned_by) VALUES(%s,%s,now(),%s)",(boat_id,berth_id,user.get('employee_id')))
            tx.execute("UPDATE boats SET current_berth_id=%s WHERE boat_id=%s",(berth_id,boat_id))

    def berth_board(self):
        return self.db.rows("""SELECT pt.port_id,pt.name port_name,p.pier_id,p.name pier,b.berth_id,b.berth_number,b.max_length,b.max_width,b.max_draft,b.daily_price,b.status,
          boat.name boat_name,boat.length boat_length,boat.width boat_width,boat.draft boat_draft,
          assignment.start_at occupied_from,assignment.end_at occupied_until,
          pickup.start_at reserved_from,pickup.end_at reserved_until,pickup.reservation_id reserved_reservation_id,
          CASE WHEN NOT pt.is_active OR NOT p.is_active THEN 'unavailable' WHEN b.status='maintenance' THEN 'maintenance' WHEN b.status='closed' THEN 'unavailable'
            WHEN boat.boat_id IS NOT NULL THEN 'occupied'
            WHEN EXISTS(SELECT 1 FROM reservations r WHERE r.pickup_berth_id=b.berth_id AND r.status_code IN('confirmed','awaiting_payment','paid','active') AND r.end_at>now()) THEN 'reserved'
            ELSE 'free' END state,
          CASE WHEN NOT pt.is_active OR NOT p.is_active THEN 'Недоступно' WHEN b.status='maintenance' THEN 'Обслуживание' WHEN b.status='closed' THEN 'Недоступно'
            WHEN boat.boat_id IS NOT NULL THEN 'Занято'
            WHEN EXISTS(SELECT 1 FROM reservations r WHERE r.pickup_berth_id=b.berth_id AND r.status_code IN('confirmed','awaiting_payment','paid','active') AND r.end_at>now()) THEN 'Зарезервировано'
            ELSE 'Свободно' END state_ru
          FROM berths b JOIN piers p USING(pier_id) JOIN ports pt USING(port_id)
          LEFT JOIN boats boat ON boat.current_berth_id=b.berth_id AND NOT boat.is_archived
          LEFT JOIN LATERAL (SELECT ba.start_at,ba.end_at FROM berth_assignments ba WHERE ba.berth_id=b.berth_id AND ba.end_at IS NULL ORDER BY ba.start_at DESC LIMIT 1) assignment ON TRUE
          LEFT JOIN LATERAL (SELECT r.reservation_id,r.start_at,r.end_at FROM reservations r WHERE r.pickup_berth_id=b.berth_id AND r.status_code IN('confirmed','awaiting_payment','paid','active') AND r.end_at>now() ORDER BY r.start_at LIMIT 1) pickup ON TRUE
          ORDER BY pt.name,p.pier_id,b.berth_number""")

    def admin_ports(self,user):
        self.require_role(user,'admin')
        return self.db.rows("""SELECT pt.*,count(DISTINCT p.pier_id) pier_count,count(DISTINCT b.berth_id) berth_count,
          count(DISTINCT boat.boat_id) boat_count FROM ports pt LEFT JOIN piers p USING(port_id)
          LEFT JOIN berths b USING(pier_id) LEFT JOIN boats boat ON boat.current_berth_id=b.berth_id AND NOT boat.is_archived
          GROUP BY pt.port_id ORDER BY pt.is_active DESC,pt.name""")

    def map_ports(self,include_inactive=False,selected_id=None):
        ports=self.db.rows("""SELECT pt.*,(SELECT image_path FROM port_images i WHERE i.port_id=pt.port_id ORDER BY i.is_cover DESC,i.image_id LIMIT 1) cover,
          COALESCE((SELECT json_agg(json_build_object('reservation_id',r.reservation_id,'boat_name',b.name,'start_at',r.start_at,'end_at',r.end_at,'status_code',r.status_code) ORDER BY r.start_at)
            FROM reservations r JOIN boats b USING(boat_id) WHERE r.port_id=pt.port_id AND r.status_code IN('paid','active') AND r.end_at>now()),'[]'::json) bookings
          FROM ports pt WHERE (%s OR pt.is_active OR pt.port_id=%s) ORDER BY pt.name""",(include_inactive,selected_id))
        board=self.berth_board()
        for index,row in enumerate(board):
            row['number']=row.pop('berth_number');row['state_ru']=row.get('state_ru') or row.get('state','')
            row['map_index']=index
            row['boat']=row.get('boat_name')
            port=next((p for p in ports if p['port_id']==row['port_id']),None)
            if port:port.setdefault('berths',[]).append(row)
        for port in ports:
            port['boats']=[{'name':r['boat_name']} for r in port.get('berths',[]) if r.get('boat_name')]
            berths=port.get('berths',[])
            counts={state:sum(1 for b in berths if b.get('state')==state) for state in ('free','occupied','reserved','unavailable','maintenance')}
            port.update({f'{state}_count':count for state,count in counts.items()})
            port['berth_count']=len(berths)
            port['pier_count']=len({b['pier_id'] for b in berths})
            if not port['is_active']:
                port['map_state']='closed';port['map_state_ru']='Порт закрыт'
            elif not berths:
                port['map_state']='unknown';port['map_state_ru']='Нет данных о местах'
            elif counts['free'] and (counts['reserved'] or counts['unavailable'] or counts['maintenance']):
                port['map_state']='partial';port['map_state_ru']='Частично ограничен'
            elif counts['free']:
                port['map_state']='available';port['map_state_ru']='Есть свободные места'
            elif counts['unavailable'] or counts['maintenance']:
                port['map_state']='partial';port['map_state_ru']='Частично ограничен'
            else:
                port['map_state']='full';port['map_state_ru']='Свободных мест нет'
            # QWebEngine receives only primitive JSON values.
            for k in ('latitude','longitude'):
                if port.get(k) is not None:port[k]=float(port[k])
            port['is_demonstration']=bool(port.get('is_demonstration'))
        return ports

    def save_port(self,user,data,port_id=None):
        self.require_role(user,'admin')
        name=str(data.get('name','')).strip()
        if not name:raise ValueError('Укажите название порта.')
        latitude=data.get('latitude');longitude=data.get('longitude')
        if (latitude is None)!=(longitude is None):raise ValueError('Укажите обе координаты или оставьте обе пустыми.')
        if latitude is not None and not(-90<=float(latitude)<=90 and -180<=float(longitude)<=180):raise ValueError('Проверьте широту и долготу.')
        values=(name,data.get('description','').strip(),data.get('address','').strip(),data.get('city','').strip(),latitude,longitude,data.get('phone','').strip(),data.get('opening_hours','').strip(),bool(data.get('is_active',True)))
        if port_id:
            old=self.db.one('SELECT is_active FROM ports WHERE port_id=%s',(port_id,))
            if old and old['is_active'] and not values[-1]:
                usage=self.db.value("""SELECT EXISTS(SELECT 1 FROM boats boat JOIN berths br ON br.berth_id=boat.current_berth_id JOIN piers p USING(pier_id) WHERE p.port_id=%s AND NOT boat.is_archived)
                  OR EXISTS(SELECT 1 FROM reservations r WHERE r.port_id=%s AND r.status_code IN('pending','confirmed','awaiting_payment','paid','active') AND r.end_at>now())""",(port_id,port_id))
                if usage:raise ValueError('Сначала перенесите яхты и завершите активные бронирования в этом порту.')
            self.db.execute('UPDATE ports SET name=%s,description=%s,address=%s,city=%s,latitude=%s,longitude=%s,phone=%s,opening_hours=%s,is_active=%s WHERE port_id=%s',values+(port_id,),user['user_id'])
        else:self.db.execute('INSERT INTO ports(name,description,address,city,latitude,longitude,phone,opening_hours,is_active) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',values,user['user_id'])

    def add_port_image(self,user,port_id,path,caption=''):
        self.require_role(user,'admin')
        with self.db.transaction(user['user_id']) as tx:
            tx.execute('UPDATE port_images SET is_cover=false WHERE port_id=%s',(port_id,))
            tx.execute('INSERT INTO port_images(port_id,image_path,caption,is_cover) VALUES(%s,%s,%s,true)',(port_id,path,caption))

    def assign_pickup_berth(self,user,reservation_id,berth_id):
        self.require_role(user,'admin','manager')
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one('SELECT r.*,c.user_id,pt.name port_name,pt.address port_address,pt.city port_city FROM reservations r JOIN clients c USING(client_id) LEFT JOIN ports pt USING(port_id) WHERE r.reservation_id=%s FOR UPDATE OF r',(reservation_id,))
            if not r or r['status_code'] not in ('confirmed','awaiting_payment','paid'):raise ValueError('Место отправления назначается подтверждённой заявке до выдачи яхты.')
            if not r['port_id']:raise ValueError('Сначала назначьте яхте активный порт на период заявки.')
            b=tx.one("""SELECT br.berth_id,br.berth_number,pt.port_id,pt.name port_name,p.name pier_name FROM berths br
              JOIN piers p USING(pier_id) JOIN ports pt USING(port_id) JOIN boats boat ON boat.boat_id=%s
              WHERE br.berth_id=%s AND pt.port_id=%s AND br.status='active' AND p.is_active AND pt.is_active AND br.max_length>=boat.length AND br.max_width>=boat.width AND br.max_draft>=boat.draft
                AND (NOT EXISTS(SELECT 1 FROM boats x WHERE x.current_berth_id=br.berth_id AND NOT x.is_archived) OR br.berth_id=boat.current_berth_id)
                AND NOT EXISTS(SELECT 1 FROM reservations other WHERE other.pickup_berth_id=br.berth_id AND other.reservation_id<>r.reservation_id
                  AND other.status_code IN('confirmed','awaiting_payment','paid','active') AND tstzrange(other.start_at,other.end_at,'[)') && tstzrange(r.start_at,r.end_at,'[)'))
              FOR UPDATE OF br""",(r['boat_id'],berth_id,r['port_id']))
            if not b:raise ValueError('Место не подходит по размеру яхты или недоступно.')
            tx.execute('UPDATE reservations SET port_id=%s,pickup_berth_id=%s,arrival_at=start_at WHERE reservation_id=%s',(b['port_id'],b['berth_id'],reservation_id))
            if b['port_id']!=r['port_id'] or b['berth_id']!=r['pickup_berth_id']:
                address=', '.join(x for x in (b['port_name'],r.get('port_address'),r.get('port_city')) if x)
                tx.execute("INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id) VALUES(%s,'Изменено место отправления',%s,'reservation','reservation',%s)",(r['user_id'],f"Для заявки №{reservation_id} изменено место отправления: {address}, причал {b['pier_name']}, место {b['berth_number']}. Прибытие: {r['start_at']:%d.%m.%Y %H:%M}.",reservation_id))

    def pickup_berth_options(self,user,reservation_id):
        self.require_role(user,'admin','manager')
        r=self.db.one('SELECT r.boat_id,r.port_id,r.start_at,r.end_at FROM reservations r WHERE r.reservation_id=%s',(reservation_id,))
        if not r or not r['port_id']:return []
        return self.db.rows("""SELECT br.berth_id,pt.name||' · '||p.name||' · место '||br.berth_number label
          FROM reservations r JOIN boats boat ON boat.boat_id=r.boat_id JOIN berths br ON br.max_length>=boat.length AND br.max_width>=boat.width AND br.max_draft>=boat.draft
          JOIN piers p USING(pier_id) JOIN ports pt USING(port_id)
          WHERE r.reservation_id=%s AND pt.port_id=r.port_id AND p.is_active AND pt.is_active AND br.status='active'
            AND (NOT EXISTS(SELECT 1 FROM boats x WHERE x.current_berth_id=br.berth_id AND NOT x.is_archived) OR br.berth_id=boat.current_berth_id)
            AND NOT EXISTS(SELECT 1 FROM reservations other WHERE other.pickup_berth_id=br.berth_id AND other.reservation_id<>r.reservation_id
              AND other.status_code IN('confirmed','awaiting_payment','paid','active') AND tstzrange(other.start_at,other.end_at,'[)') && tstzrange(r.start_at,r.end_at,'[)'))
          ORDER BY (br.berth_id=boat.current_berth_id) DESC,pt.name,p.name,br.berth_number""",(reservation_id,))

    def save_pier(self,user,data,pier_id=None):
        self.require_role(user,'admin')
        name=str(data.get('name','')).strip()
        if not name:raise ValueError('Укажите название причала.')
        port_id=data.get('port_id')
        if not port_id:raise ValueError('Выберите порт для причала.')
        active=bool(data.get('is_active',True))
        if not self.db.value('SELECT EXISTS(SELECT 1 FROM ports WHERE port_id=%s AND is_active)',(port_id,)):raise ValueError('Выберите активный порт.')
        if pier_id:
            old=self.db.one('SELECT is_active FROM piers WHERE pier_id=%s',(pier_id,))
            if old and old['is_active'] and not active:
                usage=self.db.value("""SELECT EXISTS(SELECT 1 FROM berths br JOIN boats boat ON boat.current_berth_id=br.berth_id WHERE br.pier_id=%s AND NOT boat.is_archived)
                  OR EXISTS(SELECT 1 FROM berths br JOIN reservations r ON r.pickup_berth_id=br.berth_id WHERE br.pier_id=%s AND r.status_code IN('confirmed','awaiting_payment','paid','active') AND r.end_at>now())""",(pier_id,pier_id))
                if usage:raise ValueError('Сначала перенесите яхты и завершите активные заявки с местами этого причала.')
            self.db.execute('UPDATE piers SET name=%s,location=%s,description=%s,port_id=%s,is_active=%s WHERE pier_id=%s',(name,data.get('location','').strip(),data.get('description','').strip(),port_id,active,pier_id),user['user_id'])
        else:self.db.execute('INSERT INTO piers(name,location,description,port_id,is_active) VALUES(%s,%s,%s,%s,%s)',(name,data.get('location','').strip(),data.get('description','').strip(),port_id,active),user['user_id'])

    def save_berth(self,user,data,berth_id=None):
        self.require_role(user,'admin')
        if not data.get('pier_id') or not str(data.get('berth_number','')).strip():raise ValueError('Выберите причал и укажите номер места.')
        if min(float(data['max_length']),float(data['max_width']),float(data['max_draft']))<=0 or float(data['daily_price'])<0:raise ValueError('Проверьте габариты и стоимость места.')
        if not self.db.value('SELECT EXISTS(SELECT 1 FROM piers p JOIN ports pt USING(port_id) WHERE p.pier_id=%s AND p.is_active AND pt.is_active)',(data['pier_id'],)):raise ValueError('Выберите причал активного порта.')
        values=(data['pier_id'],str(data['berth_number']).strip(),data['max_length'],data['max_width'],data['max_draft'],data['daily_price'],data['status'])
        if berth_id:self.db.execute('UPDATE berths SET pier_id=%s,berth_number=%s,max_length=%s,max_width=%s,max_draft=%s,daily_price=%s,status=%s WHERE berth_id=%s',values+(berth_id,),user['user_id'])
        else:self.db.execute('INSERT INTO berths(pier_id,berth_number,max_length,max_width,max_draft,daily_price,status) VALUES(%s,%s,%s,%s,%s,%s,%s)',values,user['user_id'])

    def admin_payments(self):
        return self.db.rows("""SELECT p.payment_id,p.reservation_id,c.first_name||' '||c.last_name client_name,b.name boat_name,
         pm.name method,p.amount,p.status,p.created_at,p.confirmed_at,p.external_reference,p.is_test
         FROM payments p JOIN clients c USING(client_id) JOIN reservations r USING(reservation_id) JOIN boats b USING(boat_id)
         JOIN payment_methods pm ON pm.payment_method_id=p.method_id ORDER BY p.created_at DESC LIMIT 500""")

    def mark_rental_issued(self,user,reservation_id,condition=""):
        self.require_role(user,'admin','manager')
        with self.db.transaction(user['user_id']) as tx:
            r=tx.one("SELECT * FROM reservations WHERE reservation_id=%s FOR UPDATE",(reservation_id,))
            if not r or r['status_code']!='paid':raise ValueError("Выдать можно только оплаченную заявку.")
            tx.execute("INSERT INTO rentals(reservation_id,actual_start,start_condition,status,final_amount) VALUES(%s,now(),%s,'issued',%s) ON CONFLICT(reservation_id) DO UPDATE SET actual_start=now(),start_condition=excluded.start_condition,status='issued'",(reservation_id,condition,r['total_amount']))
            tx.execute("UPDATE reservations SET status_code='active' WHERE reservation_id=%s",(reservation_id,))

    def mark_rental_returned(self,user,reservation_id,condition=""):
        self.require_role(user,'admin','manager')
        with self.db.transaction(user['user_id']) as tx:
            rental=tx.one("SELECT rental_id FROM rentals WHERE reservation_id=%s AND status='issued' FOR UPDATE",(reservation_id,))
            if not rental:raise ValueError("Активная выдача не найдена.")
            tx.execute("UPDATE rentals SET actual_end=now(),end_condition=%s,status='closed' WHERE rental_id=%s",(condition,rental['rental_id']))
            tx.execute("UPDATE reservations SET status_code='completed' WHERE reservation_id=%s",(reservation_id,))

    def admin_refunds(self):
        return self.db.rows("SELECT rf.*,p.reservation_id,p.amount payment_amount,p.status payment_status,c.first_name||' '||c.last_name client FROM refunds rf JOIN payments p USING(payment_id) JOIN clients c USING(client_id) ORDER BY rf.created_at DESC")

    def admin_notifications(self,user):
        self.require_role(user,'admin','manager')
        return self.db.rows("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 300",(user['user_id'],))

    def admin_audit(self,search="",start=None,end=None):
        like=f"%{search}%"
        return self.db.rows("""SELECT a.audit_id,u.email,a.action,a.entity_type,a.entity_id,a.created_at,a.details
          FROM audit_log a LEFT JOIN users u USING(user_id)
          WHERE (%s='' OR coalesce(u.email,'') ILIKE %s OR a.action ILIKE %s OR a.entity_type ILIKE %s OR a.details::text ILIKE %s)
            AND (%s::date IS NULL OR a.created_at::date>=%s::date)
            AND (%s::date IS NULL OR a.created_at::date<=%s::date)
          ORDER BY a.created_at DESC LIMIT 500""",(search,like,like,like,like,start,start,end,end))

    def analytics(self,start:date,end:date):
        return {
          'revenue':self.db.rows("SELECT * FROM fn_get_monthly_revenue(%s,%s)",(start,end)),
          'boats':self.db.rows("SELECT * FROM fn_get_boat_popularity(%s,%s)",(start,end)),
          'utilization':self.db.rows("SELECT * FROM fn_get_fleet_utilization(%s,%s)",(start,end)),
          'bookings_monthly':self.db.rows("""SELECT date_trunc('month',created_at)::date AS month_date,count(*) AS bookings FROM reservations
            WHERE created_at::date BETWEEN %s AND %s AND status_code NOT IN('cancelled','rejected','expired')
            GROUP BY 1 ORDER BY 1""",(start,end)),
          'revenue_by_boat':self.db.rows("""SELECT b.name boat_name,count(*) bookings,COALESCE(sum(r.total_amount),0) revenue FROM reservations r
            JOIN boats b USING(boat_id) WHERE r.created_at::date BETWEEN %s AND %s AND r.status_code NOT IN('cancelled','rejected','expired')
            GROUP BY b.boat_id,b.name ORDER BY revenue DESC LIMIT 10""",(start,end)),
          'comparison':self.db.one("""SELECT
            COALESCE(sum(p.amount) FILTER(WHERE p.status IN('confirmed','partially_refunded') AND p.confirmed_at::date BETWEEN %s AND %s),0) current_revenue,
            COALESCE(sum(p.amount) FILTER(WHERE p.status IN('confirmed','partially_refunded') AND p.confirmed_at::date BETWEEN %s AND %s),0) previous_revenue
            FROM payments p""",(start,end,start-(end-start+date.resolution),start-date.resolution)),
          'statuses':self.db.rows("SELECT status_code,count(*) count FROM reservations WHERE created_at::date BETWEEN %s AND %s GROUP BY status_code ORDER BY status_code",(start,end)),
          'types':self.db.rows("SELECT bt.name,count(*) bookings,sum(r.total_amount) revenue FROM reservations r JOIN boats b USING(boat_id) JOIN boat_types bt USING(boat_type_id) WHERE r.created_at::date BETWEEN %s AND %s AND r.status_code NOT IN('cancelled','rejected') GROUP BY bt.name ORDER BY revenue DESC",(start,end)),
          'clients':self.db.rows("SELECT c.first_name||' '||c.last_name name,sum(r.total_amount) spending,count(*) orders FROM reservations r JOIN clients c USING(client_id) WHERE r.created_at::date BETWEEN %s AND %s GROUP BY c.client_id ORDER BY spending DESC LIMIT 10",(start,end)),
          'weather':self.db.rows("SELECT safety_level,count(*) count FROM weather_observations WHERE observed_at::date BETWEEN %s AND %s GROUP BY safety_level",(start,end)),
        }

    def weather_history(self,limit=96):
        return self.db.rows("SELECT * FROM weather_observations ORDER BY observed_at DESC LIMIT %s",(limit,))

    def latest_weather(self):
        return self.db.one("SELECT * FROM weather_observations WHERE NOT is_forecast ORDER BY observed_at DESC LIMIT 1")

    def save_weather(self,observations):
        with self.db.transaction() as tx:
            for d in observations:
                tx.execute("""INSERT INTO weather_observations(observed_at,temperature,wind_speed,wind_direction,wind_gust,precipitation,precipitation_probability,cloud_cover,visibility_km,weather_code,condition,safety_level,latitude,longitude,source,is_forecast)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Open-Meteo',%s) ON CONFLICT DO NOTHING""",
                (d['observed_at'],d.get('temperature'),d.get('wind_speed'),d.get('wind_direction'),d.get('wind_gust'),d.get('precipitation'),d.get('precipitation_probability'),d.get('cloud_cover'),d.get('visibility_km'),d.get('weather_code'),d.get('condition',''),d.get('safety_level','unknown'),d.get('latitude'),d.get('longitude'),d.get('is_forecast',False)))
