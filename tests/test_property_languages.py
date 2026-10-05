from test_properties import migrated_connection
from test_property_creation import client, form_data

def test_arabic_default(client):
    page = client.get('/admin/properties/new').get_data(as_text=True)
    assert 'dir="rtl"' in page
    assert 'ماذا تريد أن تفعل بعقارك؟' in page

def test_english_ltr(client):
    page = client.get('/admin/properties/new?lang=en').get_data(as_text=True)
    assert 'dir="ltr"' in page
    assert 'For Rent' in page

def test_single_content_language(client):
    page = client.get('/admin/properties/new?lang=en').get_data(as_text=True)
    assert 'name="title_en"' not in page and 'name="description_en"' not in page
    assert 'name="title_ar"' in page and 'name="description_ar"' in page
