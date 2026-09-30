from test_properties import migrated_connection
from sqlalchemy import select
from app import db
from app.models import Property
from app.states import SUDAN_STATES
from test_property_creation import client, form_data
import pytest

@pytest.mark.parametrize('language,index', [('ar',1),('en',0)])
def test_approved_states(client, language, index):
    page = client.get('/admin/properties/new' + ('?lang=en' if language == 'en' else '')).get_data(as_text=True)
    for state in SUDAN_STATES:
        assert state[index] in page

@pytest.mark.parametrize('state', SUDAN_STATES)
def test_state_and_neighborhood_saved(client, form_data, state):
    response = client.post('/admin/properties', data=form_data | {'state_en':state[0], 'neighborhood_ar':'حي جديد'})
    assert response.status_code == 303
    saved = db.session.scalar(select(Property).order_by(Property.id.desc()))
    assert (saved.state_en,saved.state_ar) == state
    assert saved.neighborhood_ar == 'حي جديد'
    assert saved.city_ar is None and saved.area_ar is None
