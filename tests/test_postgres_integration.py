"""Requires a running Docker PostgreSQL instance initialised by main.py/Compose."""
from datetime import date,timedelta

import pytest
import psycopg

from yachtclub.config import load_settings
from yachtclub.db import Db
from yachtclub.service import YachtService


@pytest.fixture(scope='module')
def db():
    database=Db(load_settings())
    yield database
    database.close()


def test_demo_dataset_meets_minimums(db):
    counts=db.one("""SELECT
      (SELECT count(*) FROM clients) clients,
      (SELECT count(*) FROM boats) boats,
      (SELECT count(*) FROM reservations) reservations,
      (SELECT count(*) FROM payments) payments,
      (SELECT count(*) FROM maintenance) maintenance,
      (SELECT count(*) FROM weather_observations WHERE source<>'Демонстрационный набор') weather,
      (SELECT count(*) FROM boat_images) images""")
    assert counts['clients']>=30 and counts['boats']>=20 and counts['reservations']>=100
    assert counts['payments']>=100 and counts['maintenance']>=20
    # Weather is optional until the real provider returns observations; synthetic
    # demo readings must never be used to satisfy the dataset requirement.
    assert db.value("SELECT count(*) FROM weather_observations WHERE source='Демонстрационный набор'")==0
    assert counts['images']>=40


def test_admin_can_sign_in(db):
    user=YachtService(db).authenticate('admin@yacht.local','Captain123!')
    assert user['role_name']=='admin'
    assert user['employee_id'] is not None


def test_price_and_availability_functions(db):
    boat=db.one("SELECT boat_id FROM boats WHERE NOT is_archived ORDER BY boat_id LIMIT 1")
    client=db.one("SELECT client_id FROM clients ORDER BY client_id LIMIT 1")
    quote=db.one("SELECT * FROM fn_calculate_reservation_total(%s,%s,now()+interval '90 day',now()+interval '90 day 4 hour',2)",(boat['boat_id'],client['client_id']))
    assert quote and quote['base_amount']>0 and quote['capacity_ok']
    available=db.rows("SELECT * FROM fn_get_available_boats(now()+interval '300 day',now()+interval '300 day 4 hour',1)")
    assert isinstance(available,list)


def test_database_rejects_overlapping_boat_period(db):
    existing=db.one("""SELECT boat_id,client_id,start_at,end_at FROM reservations
       WHERE status_code IN('pending','confirmed','awaiting_payment','paid','active') ORDER BY reservation_id LIMIT 1""")
    with db.pool.connection() as conn:
        with pytest.raises(psycopg.errors.ExclusionViolation):
            conn.execute("""INSERT INTO reservations(client_id,boat_id,start_at,end_at,passenger_count,status_code,total_amount)
              VALUES(%s,%s,%s,%s,1,'pending',1)""",(existing['client_id'],existing['boat_id'],existing['start_at'],existing['end_at']))
        conn.rollback()


def test_receipt_is_only_created_for_confirmed_payment(db):
    invalid=db.value("SELECT count(*) FROM receipts rc JOIN payments p USING(payment_id) WHERE p.status NOT IN('confirmed','partially_refunded','refunded')")
    assert invalid==0


def test_dashboard_views_return_data(db):
    assert db.value('SELECT count(*) FROM vw_boat_catalog')>=20
    assert db.value('SELECT count(*) FROM vw_boat_statistics')>=20
    assert db.value('SELECT count(*) FROM vw_payment_summary')>=100

