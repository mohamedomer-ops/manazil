import re
from flask import current_app
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import scoped_session, sessionmaker
from app import db
from app.models import Property, User
from app.property_forms import FORM_DEFAULTS
from test_properties import migrated_connection

@pytest.fixture
def client(migrated_connection, monkeypatch):
    sessions = scoped_session(sessionmaker(bind=migrated_connection, join_transaction_mode="create_savepoint"))
    monkeypatch.setattr(db, "session", sessions)
    try:
        user = User(phone_number='+249912345678', is_verified=True, is_active=True)
        db.session.add(user)
        db.session.commit()
        test_client = current_app.test_client()
        with test_client.session_transaction() as auth_session:
            auth_session['user_id'] = user.id
        yield test_client
    finally:
        sessions.remove()

@pytest.fixture
def form_data(client):
    page = client.get('/admin/properties/new?lang=en').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    photo_token = re.search(r'name="_photo_token" value="([^"]+)"', page).group(1)
    return {**FORM_DEFAULTS, 'csrf_token':csrf, '_photo_token':photo_token, '_language':'en',
            'property_type':'apartment', 'title_ar':'شقة', 'description_ar':'وصف شقة',
            'bedrooms':'2', 'bathrooms':'1', 'size':'100', 'furnished':'on',
            'amenities':'Parking\nKitchen', 'price':'125000', 'currency':'SDG',
            'contact_name':'Ahmed', 'phone':'+249123456789', 'whatsapp':'',
            'state_en':'Khartoum', 'neighborhood_ar':'الرياض'}

def property_count():
    return db.session.scalar(select(func.count()).select_from(Property))

def test_single_page_sections(client):
    page = client.get('/admin/properties/new').get_data(as_text=True)
    assert page.index('التصنيف') < page.index('ماذا تعرض؟') < page.index('الصور') < page.index('تفاصيل العقار') < page.index('بيانات التواصل') < page.index('الموقع')
    assert 'wizard-progress' not in page and 'name="_step"' not in page
    assert 'name="city_ar"' not in page and 'name="area_ar"' not in page
    assert 'photos_exterior' not in page
    assert 'انشر العقار' in page and 'إرسال للمراجعة' not in page

@pytest.mark.parametrize('transaction,period,occupancy,agent', [
    ('rent','monthly','room','yes'), ('rent','weekly','entire_property','no'),
    ('sale','','room','no'), ('sale','','entire_property','yes')])
def test_submit_for_review(client, form_data, transaction, period, occupancy, agent):
    data = form_data | {'transaction_type':transaction, 'rent_period':period, 'property_occupancy':occupancy, 'agent':agent}
    response = client.post('/admin/properties', data=data)
    assert response.status_code == 303
    saved = db.session.scalar(select(Property).order_by(Property.id.desc()))
    assert saved.publication_status == 'published'
    assert saved.owner_id is not None
    assert saved.transaction_type == transaction and saved.rent_period == (period or None)
    assert saved.property_occupancy == occupancy
    assert saved.contact_role == ('broker' if agent == 'yes' else 'owner')
    assert saved.price == 125000 and saved.monthly_rent is None
    assert saved.neighborhood_ar == 'الرياض' and saved.city_ar is None and saved.area_ar is None

@pytest.mark.parametrize('field,value', [('transaction_type','bad'),('property_occupancy','bad'),('agent','bad'),('price','-1'),('price','NaN'),('price','abc'),('price',''),('rent_period','bad'),('state_en','Atlantis'),('neighborhood_ar',''),('phone',''),('property_type','bad'),('bedrooms','-1'),('contact_name','')])
def test_invalid_input(client, form_data, field, value):
    before = property_count()
    response = client.post('/admin/properties', data=form_data | {field:value})
    assert response.status_code == 422
    assert property_count() == before

def test_sale_rejects_rent_period(client, form_data):
    response = client.post('/admin/properties', data=form_data | {'transaction_type':'sale','rent_period':'weekly'})
    assert response.status_code == 422

def test_csrf(client, form_data):
    for token in ('', 'invalid'):
        assert client.post('/admin/properties', data=form_data | {'csrf_token':token}).status_code == 400


def test_completed_listing_is_public_immediately(client, form_data):
    response = client.post('/admin/properties', data=form_data)
    assert response.status_code == 303
    saved = db.session.scalar(select(Property).order_by(Property.id.desc()))
    assert saved.publication_status == 'published'
    assert response.headers['Location'].endswith(f'/properties/{saved.id}?lang=en')
    assert client.get('/properties?lang=en').get_data(as_text=True).find('شقة') >= 0
    assert client.get(f'/properties/{saved.id}?lang=en').status_code == 200
    assert {item[0] for item in db.session.execute(select(Property.publication_status)).all()} == {'published'}


def test_incomplete_submission_stays_unpublished(client, form_data):
    before = property_count()
    assert client.post('/admin/properties', data=form_data | {'phone': ''}).status_code == 422
    assert property_count() == before


def test_approval_routes_are_removed(client):
    assert client.get('/admin/properties/pending').status_code == 404
    assert client.post('/admin/properties/1/approve').status_code == 404
    assert client.post('/admin/properties/1/reject').status_code == 404
