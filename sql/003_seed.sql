-- Linked demo data. All test accounts use the password documented in README.md.
INSERT INTO roles(role_name,description) VALUES
 ('client','Клиент яхт-клуба'),('admin','Администратор'),('manager','Менеджер бронирований')
ON CONFLICT(role_name) DO NOTHING;
INSERT INTO positions(position_name) VALUES('Администратор'),('Менеджер'),('Капитан'),('Механик'),('Бухгалтер') ON CONFLICT DO NOTHING;
INSERT INTO membership_types(name,discount_percent,annual_price,description) VALUES
 ('Стандартное',0,0,'Обычная аренда'),('Серебряное',5,12000,'Скидка 5%'),('Золотое',10,30000,'Приоритетное бронирование'),('VIP',15,60000,'Расширенные привилегии')
ON CONFLICT(name) DO NOTHING;
INSERT INTO boat_types(name,description,max_wind_speed,max_wind_gust) VALUES
 ('Парусная яхта','Для неспешных морских прогулок',28,38),('Моторная яхта','Комфортные скоростные прогулки',35,48),
 ('Катер','Компактные дневные маршруты',32,44),('Катамаран','Просторный двухкорпусный флот',30,42),
 ('Премиум яхта','Просторные суда для особых событий',36,50)
ON CONFLICT(name) DO NOTHING;
INSERT INTO manufacturers(name,country) VALUES
 ('Beneteau','Франция'),('Jeanneau','Франция'),('Bavaria','Германия'),('Azimut','Италия'),
 ('Sunseeker','Великобритания'),('Lagoon','Франция'),('Princess','Великобритания'),('Galeon','Польша')
ON CONFLICT(name) DO NOTHING;
INSERT INTO boat_statuses(code,name,description) VALUES
 ('available','Свободна','Доступна для заявки'),('reserved','Забронирована','Назначено бронирование'),
 ('rented','В аренде','Сейчас используется'),('maintenance','Обслуживание','На плановых работах'),('unavailable','Недоступна','Эксплуатация запрещена')
ON CONFLICT(code) DO NOTHING;
INSERT INTO reservation_statuses(code,title,is_terminal) VALUES
 ('pending','Ожидает подтверждения',false),('confirmed','Подтверждено',false),('awaiting_payment','Ожидает оплаты',false),
 ('paid','Оплачено',false),('active','Активно',false),('completed','Завершено',true),('rejected','Отклонено',true),
 ('cancelled','Отменено',true),('expired','Истёк срок оплаты',true)
ON CONFLICT(code) DO NOTHING;
INSERT INTO cancellation_reasons(name,description) VALUES
 ('Погодные условия','Ограничения по правилам безопасности'),('Клиент','Отмена клиентом'),('Техническая причина','Неисправность яхты'),
 ('Изменение планов','Перенос или смена дат'),('Другое','Иная причина') ON CONFLICT(name) DO NOTHING;
INSERT INTO payment_methods(name) VALUES('Демо-оплата'),('Банковский перевод'),('Наличные'),('Банковская карта') ON CONFLICT(name) DO NOTHING;
INSERT INTO maintenance_types(name,description) VALUES
 ('Плановый осмотр','Регламентная проверка'),('Двигатель','Диагностика и ремонт двигателя'),('Корпус','Осмотр и ремонт корпуса'),
 ('Навигация','Проверка навигационного оборудования'),('Электрика','Проверка электрики') ON CONFLICT(name) DO NOTHING;
INSERT INTO amenities(name,description) VALUES
 ('Кондиционер','Климат-контроль'),('Кухня','Камбуз на борту'),('Душ','Душевая зона'),('Аудиосистема','Музыка на борту'),
 ('Навигация','Навигационное оборудование'),('Спасательное оборудование','Жилеты и аптечка'),('Солнечная палуба','Место для отдыха'),
 ('Wi-Fi','Связь на борту'),('Рыболовное оборудование','Снасти'),('SUP-доска','Доска для прогулок') ON CONFLICT(name) DO NOTHING;
INSERT INTO piers(name,location,description) VALUES
 ('Северная марина','Основная гавань','Причал с сервисной зоной'),('Южная марина','Южная бухта','Гостевые места'),
 ('Восточная марина','Восточная набережная','Тихая стоянка'),('Премиум причал','Центральная гавань','Места повышенного комфорта')
ON CONFLICT(name) DO NOTHING;

INSERT INTO users(role_id,email,password_hash) VALUES
 ((SELECT role_id FROM roles WHERE role_name='admin'),'admin@yacht.local',crypt('Captain123!',gen_salt('bf',12)))
ON CONFLICT(email) DO NOTHING;
INSERT INTO employees(user_id,position_id,first_name,last_name,hire_date)
SELECT u.user_id,p.position_id,'Алексей','Морской',CURRENT_DATE-1200 FROM users u CROSS JOIN positions p
WHERE u.email='admin@yacht.local' AND p.position_name='Администратор'
ON CONFLICT(user_id) DO NOTHING;

INSERT INTO users(role_id,email,password_hash,created_at)
SELECT (SELECT role_id FROM roles WHERE role_name='client'),'client'||lpad(n::text,2,'0')||'@example.test',crypt('Client123!',gen_salt('bf',10)),now()-n*interval '5 day'
FROM generate_series(1,35) n ON CONFLICT(email) DO NOTHING;
INSERT INTO clients(user_id,first_name,last_name,phone,birth_date,registered_at)
SELECT u.user_id,(ARRAY['Александр','Мария','Илья','Анна','Дмитрий','Елена','Павел','София'])[(n%8)+1],
 (ARRAY['Морозов','Иванова','Петров','Смирнова','Орлов','Волкова','Кузнецов'])[(n%7)+1],
 format('+7 978 200-%s',lpad(n::text,4,'0')),DATE '1980-01-01'+n*interval '220 day',u.created_at
FROM generate_series(1,35) n JOIN users u ON u.email='client'||lpad(n::text,2,'0')||'@example.test'
ON CONFLICT(user_id) DO NOTHING;
INSERT INTO memberships(client_id,membership_type_id,start_date,end_date,status)
SELECT c.client_id,((c.client_id-1)%4+1),CURRENT_DATE-180,CURRENT_DATE+185,'active'
FROM clients c WHERE c.client_id<=35 AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.client_id=c.client_id);

INSERT INTO berths(pier_id,berth_number,max_length,max_width,max_draft,daily_price)
SELECT ((g-1)/8)+1,'M-'||lpad(((g-1)%8+1)::text,2,'0'),22,7,3.5,1500+g*50 FROM generate_series(1,32) g
ON CONFLICT(pier_id,berth_number) DO NOTHING;
INSERT INTO boats(name,model,boat_type_id,manufacturer_id,status_id,current_berth_id,production_year,length,width,draft,capacity,cabin_count,bathroom_count,engine_power,hourly_rate,daily_rate,min_hours,deposit_amount,description,equipment)
SELECT format('%s %s',CASE ((g-1)%5) WHEN 0 THEN 'Морской бриз' WHEN 1 THEN 'Синяя лагуна' WHEN 2 THEN 'Белый парус' WHEN 3 THEN 'Атлантика' ELSE 'Лазурный берег' END,lpad(g::text,2,'0')),
format('%s %s',bt.name,100+g),bt.boat_type_id,m.manufacturer_id,(SELECT boat_status_id FROM boat_statuses WHERE code='available'),g,
2013+(g%12),7+(g%11),2.7+(g%5)*0.35,1.2+(g%4)*0.25,6+(g%7)*2,1+(g%5),1+(g%3),120+g*18,
4000+g*550,26000+g*2700,3,15000+g*600,
'Демонстрационная карточка яхты с описанием маршрутов, комфорта и условий выхода.',
 'Спасательные жилеты, навигация, аудиосистема, тент'
FROM generate_series(1,25) g JOIN boat_types bt ON bt.boat_type_id=((g-1)%5+1)
JOIN manufacturers m ON m.manufacturer_id=((g-1)%8+1)
WHERE NOT EXISTS(SELECT 1 FROM boats b WHERE b.name=format('%s %s',CASE ((g-1)%5) WHEN 0 THEN 'Морской бриз' WHEN 1 THEN 'Синяя лагуна' WHEN 2 THEN 'Белый парус' WHEN 3 THEN 'Атлантика' ELSE 'Лазурный берег' END,lpad(g::text,2,'0')));
INSERT INTO boat_images(boat_id,image_path,caption,alt_text,sort_order,is_cover)
SELECT b.boat_id,format('assets/boats/%s.svg',CASE WHEN bt.name LIKE '%Парус%' THEN 'sailboat' WHEN bt.name LIKE '%Катамаран%' THEN 'catamaran' WHEN bt.name LIKE '%Катер%' THEN 'speedboat' WHEN bt.name LIKE '%Премиум%' THEN 'premium' ELSE 'motor-yacht' END),
 b.name||' — демонстрационная иллюстрация', 'Иллюстрация яхты '||b.name,idx,idx=1
FROM boats b JOIN boat_types bt USING(boat_type_id) CROSS JOIN generate_series(1,3) idx
WHERE NOT EXISTS(SELECT 1 FROM boat_images i WHERE i.boat_id=b.boat_id AND i.sort_order=idx);
INSERT INTO boat_amenities(boat_id,amenity_id)
SELECT b.boat_id,((b.boat_id+i-1)%10)+1 FROM boats b CROSS JOIN generate_series(1,5) i ON CONFLICT DO NOTHING;
INSERT INTO safety_rules(boat_type_id,warning_wind_speed,danger_wind_speed,warning_gust,danger_gust)
SELECT boat_type_id,max_wind_speed*0.8,max_wind_speed,max_wind_gust*0.8,max_wind_gust FROM boat_types ON CONFLICT(boat_type_id) DO NOTHING;
INSERT INTO services(name,description,price,pricing_unit) VALUES
 ('Капитан','Сопровождение капитаном',5000,'за час'),('Топливо','Дополнительный запас топлива',3500,'за заказ'),
 ('Кейтеринг','Питание на борту',2500,'на человека'),('Снаряжение для снорклинга','Комплект масок и ласт',1200,'за комплект'),
 ('Трансфер','Трансфер до марины',1800,'за поездку'),('Уборка','Послерейсовая уборка',1500,'за заказ'),
 ('Пледы и полотенца','Комплект на борту',700,'за комплект'),('Рыболовное оборудование','Снасти',1300,'за комплект'),
 ('Гид','Экскурсионное сопровождение',4000,'за час'),('Праздничное оформление','Декор на борту',6500,'за заказ'),
 ('Фотоуслуги','Фотограф на борту',7000,'за заказ'),('Дополнительная страховка','Расширенное покрытие',2000,'за заказ')
ON CONFLICT(name) DO NOTHING;
INSERT INTO service_boat_types(service_id,boat_type_id)
SELECT s.service_id,t.boat_type_id FROM services s CROSS JOIN boat_types t ON CONFLICT DO NOTHING;

INSERT INTO reservations(client_id,boat_id,start_at,end_at,passenger_count,status_code,total_amount,discount_percent,created_at,customer_comment,cancellation_reason_id)
SELECT ((g-1)%35)+1,((g-1)%25)+1,
 (CURRENT_DATE-45+((g-1)/25)*25+(g%6)*2)::timestamp + time '10:00',
 (CURRENT_DATE-45+((g-1)/25)*25+(g%6)*2)::timestamp + time '14:00',
 2+(g%7),
 (ARRAY['completed','completed','paid','confirmed','pending','awaiting_payment','cancelled','rejected','active'])[(g%9)+1],
 round((12000+g*850)::numeric*(1-((g%4)*0.03)),2),((g%4)*3),now()-((g%90)+1)*interval '1 day',
 CASE WHEN g%8=0 THEN 'Праздничный маршрут' ELSE '' END,
 CASE WHEN (ARRAY['completed','completed','paid','confirmed','pending','awaiting_payment','cancelled','rejected','active'])[(g%9)+1]='cancelled' THEN 1 ELSE NULL END
FROM generate_series(1,120) g
WHERE NOT EXISTS(SELECT 1 FROM reservations r WHERE r.client_id=((g-1)%35)+1 AND r.boat_id=((g-1)%25)+1 AND r.created_at::date=(now()-((g%90)+1)*interval '1 day')::date);
INSERT INTO reservation_services(reservation_id,service_id,quantity,unit_price_snapshot)
SELECT r.reservation_id,((r.reservation_id+i-1)%12)+1,CASE WHEN i=1 THEN 1 ELSE 2 END,s.price
FROM reservations r CROSS JOIN generate_series(1,CASE WHEN r.reservation_id%3=0 THEN 2 ELSE 1 END) i
JOIN services s ON s.service_id=((r.reservation_id+i-1)%12)+1
WHERE r.reservation_id<=80 ON CONFLICT DO NOTHING;
UPDATE reservations r SET total_amount=round(
 (CASE WHEN extract(epoch FROM(r.end_at-r.start_at))/3600>=24 THEN ceil(extract(epoch FROM(r.end_at-r.start_at))/86400)*b.daily_rate
 ELSE extract(epoch FROM(r.end_at-r.start_at))/3600*b.hourly_rate END)*(1-r.discount_percent/100)
 +COALESCE((SELECT sum(quantity*unit_price_snapshot) FROM reservation_services rs WHERE rs.reservation_id=r.reservation_id),0),2)
FROM boats b WHERE b.boat_id=r.boat_id AND r.reservation_id<=120;
INSERT INTO reservation_status_history(reservation_id,new_status_code,note)
SELECT reservation_id,status_code,'Начальное демонстрационное состояние' FROM reservations
WHERE NOT EXISTS(SELECT 1 FROM reservation_status_history h WHERE h.reservation_id=reservations.reservation_id);
INSERT INTO rentals(reservation_id,actual_start,actual_end,start_condition,end_condition,final_amount,status)
SELECT r.reservation_id,r.start_at,CASE WHEN r.status_code='completed' THEN r.end_at ELSE NULL END,'Состояние зафиксировано перед выдачей',
 CASE WHEN r.status_code='completed' THEN 'Демонстрационное возвращение без замечаний' ELSE '' END,r.total_amount,
 CASE WHEN r.status_code='completed' THEN 'closed' ELSE 'scheduled' END
FROM reservations r WHERE r.status_code IN('completed','active','paid') AND r.reservation_id<=90
AND NOT EXISTS(SELECT 1 FROM rentals x WHERE x.reservation_id=r.reservation_id) LIMIT 75;

INSERT INTO payments(reservation_id,client_id,method_id,amount,status,created_at,confirmed_at,is_test,note)
SELECT r.reservation_id,r.client_id,((r.reservation_id-1)%4)+1,
 CASE WHEN r.reservation_id%8=0 THEN round(r.total_amount*0.4,2) ELSE r.total_amount END,
 CASE WHEN r.reservation_id%7=0 THEN 'pending_confirmation' WHEN r.reservation_id%11=0 THEN 'declined' ELSE 'confirmed' END,
 r.created_at+interval '1 hour',CASE WHEN r.reservation_id%7=0 OR r.reservation_id%11=0 THEN NULL ELSE r.created_at+interval '2 hour' END,
 r.reservation_id%3=0,'Связанный демонстрационный платёж'
FROM reservations r WHERE r.reservation_id<=110
AND NOT EXISTS(SELECT 1 FROM payments p WHERE p.reservation_id=r.reservation_id);
INSERT INTO refunds(payment_id,amount,reason,status,created_at,processed_at)
SELECT p.payment_id,LEAST(round(p.amount*0.25,2),p.amount-0.01),'Демонстрационный частичный возврат','processed',p.created_at+interval '2 day',p.created_at+interval '3 day'
FROM payments p WHERE p.payment_id%13=0 AND p.status='confirmed'
AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.payment_id);
UPDATE payments p SET status='partially_refunded' FROM refunds r WHERE r.payment_id=p.payment_id AND r.status='processed' AND p.status='confirmed';
INSERT INTO receipts(payment_id,receipt_number,total_amount)
SELECT p.payment_id,'YC-DEMO-'||lpad(p.payment_id::text,8,'0'),p.amount FROM payments p
WHERE p.status IN('confirmed','partially_refunded') ON CONFLICT(payment_id) DO NOTHING;

INSERT INTO maintenance(boat_id,type_id,employee_id,start_at,end_at,description,work_performed,cost,status,next_inspection_date)
SELECT ((g-1)%25)+1,((g-1)%5)+1,(SELECT employee_id FROM employees ORDER BY employee_id LIMIT 1),
 CURRENT_DATE-(g*9),CASE WHEN g%5=0 THEN NULL ELSE CURRENT_DATE-(g*9)+2 END,
 'Плановое обслуживание и проверка систем',CASE WHEN g%5=0 THEN '' ELSE 'Осмотр и проверка выполнены' END,5000+g*1200,
 CASE WHEN g%5=0 THEN 'in_progress' ELSE 'completed' END,CURRENT_DATE+g+15
FROM generate_series(1,25) g
WHERE NOT EXISTS(SELECT 1 FROM maintenance m WHERE m.boat_id=((g-1)%25)+1 AND m.start_at=CURRENT_DATE-(g*9));
INSERT INTO berth_assignments(boat_id,berth_id,start_at,assigned_by)
SELECT b.boat_id,b.current_berth_id,now()-interval '100 day',(SELECT employee_id FROM employees ORDER BY employee_id LIMIT 1)
FROM boats b WHERE b.current_berth_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM berth_assignments a WHERE a.boat_id=b.boat_id AND a.end_at IS NULL);

INSERT INTO notifications(user_id,title,message,notification_type,related_entity,related_id)
SELECT u.user_id,'Добро пожаловать','Это демонстрационное уведомление клиентского кабинета.','info','client',c.client_id
FROM clients c JOIN users u USING(user_id) WHERE c.client_id<=10;
INSERT INTO reviews(client_id,boat_id,reservation_id,rating,comment,moderation_status)
SELECT r.client_id,r.boat_id,r.reservation_id,3+(r.reservation_id%3),'Демонстрационный отзыв после аренды','approved'
FROM reservations r WHERE r.status_code='completed' ORDER BY r.reservation_id LIMIT 12
ON CONFLICT(reservation_id) DO NOTHING;
