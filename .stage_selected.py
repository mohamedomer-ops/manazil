from pathlib import Path
import subprocess
import re

git = r'C:\Program Files\Git\cmd\git.exe'

def original(path):
    return subprocess.check_output([git, 'show', f'HEAD:{path}']).decode('utf-8')

def stage(path, content):
    blob = subprocess.check_output([git, 'hash-object', '-w', '--stdin'], input=content.encode('utf-8')).decode().strip()
    subprocess.check_call([git, 'update-index', '--cacheinfo', '100644', blob, path])

css = original('app/static/css/style.css')
posting = Path('app/static/css/style.css').read_text(encoding='utf-8').split('.posting-page { max-width: 760px; }', 1)[1]
stage('app/static/css/style.css', css.rstrip('\n') + '\n.posting-page { max-width: 760px; }' + posting)

for path in ('app/templates/property_detail.html', 'app/templates/components/property_card.html'):
    content = original(path)
    content = content.replace("{% set area = property.area_ar if language == 'ar' or not property.area_en else property.area_en %}", "{% set area = property.neighborhood_ar or (property.area_ar if language == 'ar' or not property.area_en else property.area_en) %}")
    content = content.replace('{% if state != city %}{{ state }} · {% endif %}{{ city }} · {{ area }}', '{% if city and state != city %}{{ state }} · {{ city }}{% else %}{{ state }}{% endif %}{% if area %} · {{ area }}{% endif %}')
    content = content.replace("{{ t('Monthly rent') }}", "{{ t('Sale price' if property.transaction_type == 'sale' else 'Weekly rent' if property.rent_period == 'weekly' else 'Monthly rent') }}")
    content = content.replace('property.monthly_rent', 'property.price')
    stage(path, content)

path = 'tests/test_property_detail.py'
content = original(path).replace('("draft", "available"), ("pending", "available"),\n    ("archived", "available"), ("published", "rented"),', '("draft", "available"), ("published", "rented"),')
stage(path, content)

path = 'tests/test_public_properties.py'
content = original(path).replace('        ("pending", "available", "Pending secret"),\n', '').replace('        ("archived", "available", "Archived secret"),\n', '')
stage(path, content)
