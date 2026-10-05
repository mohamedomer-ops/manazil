from test_properties import migrated_connection
from test_property_creation import client, form_data

def test_no_wizard_navigation(client):
    page = client.get('/admin/properties/new?lang=en').get_data(as_text=True)
    assert 'Step 1' not in page and 'wizard-progress' not in page
    assert 'value="next"' not in page and 'value="back"' not in page
    headings = ['id="category-heading"', 'What are you renting?', 'id="photos-heading"',
                'id="details-heading"', 'id="amenities-heading"', 'id="contact-heading"',
                'id="location-heading"']
    positions = [page.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert page.count('id="property-form"') == 1

def test_language_switch_preserves_entries(client, form_data):
    response = client.post('/admin/properties', data=form_data | {'_action':'switch_ar'})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'شقة' in page and 'الخرطوم' in page
