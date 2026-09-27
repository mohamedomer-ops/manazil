import io
import re

import pytest
from flask import current_app
from PIL import Image
from sqlalchemy import func, select

from app import db
from app.models import DRAFT_OPTIONAL_TEXT_FIELDS, PHOTO_CATEGORIES, Property, PropertyPhoto
from app.photo_storage import LocalPhotoStorage, MAX_PHOTO_BYTES
from test_properties import migrated_connection, values
from test_property_creation import client, form_data, property_count
from test_property_languages import FormHTML


@pytest.fixture
def photo_client(client, tmp_path):
    current_app.config["PHOTO_STORAGE_ROOT"] = str(tmp_path)
    return client


def image_file(fmt="JPEG", name=None, color="green"):
    extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[fmt]
    output = io.BytesIO()
    Image.new("RGB", (24, 18), color).save(output, format=fmt)
    output.seek(0)
    return output, name or f"room.{extension}", f"image/{'jpeg' if fmt == 'JPEG' else fmt.lower()}"


def step_five(client):
    initial = client.get("/admin/properties/new?lang=en")
    return client.post("/admin/properties", data=FormHTML(initial).values | {
        "_step": "5", "_action": "switch_en",
    })


def post_action(client, page, action, **extra):
    return client.post("/admin/properties", data=FormHTML(page).values | extra | {"_action": action})


def upload(client, page, category="exterior", file=None):
    return post_action(client, page, f"upload_{category}",
                       **{f"photos_{category}": file or image_file()})


def staged(client, page):
    return LocalPhotoStorage().read(FormHTML(page).values["_photo_token"])["photos"]


@pytest.mark.parametrize("fmt,content_type", [
    ("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp"),
])
def test_valid_photo_formats_and_staged_preview(photo_client, fmt, content_type):
    page = upload(photo_client, step_five(photo_client), file=image_file(fmt))
    assert page.status_code == 200
    photos = staged(photo_client, page)
    assert len(photos) == 1
    assert photos[0]["content_type"] == content_type
    assert photos[0]["is_primary"] is True
    assert photos[0]["storage_key"].startswith("staging/")
    assert photos[0]["original_filename"] not in photos[0]["storage_key"]
    assert "1 / 4" in page.get_data(as_text=True)
    preview = photo_client.get(f"/admin/properties/staged-photos/{FormHTML(page).values['_photo_token']}/{photos[0]['id']}")
    assert preview.status_code == 200
    assert preview.mimetype == content_type
    assert property_count() == 0


@pytest.mark.parametrize("file,error_fragment", [
    ((io.BytesIO(b"GIF89a"), "room.gif", "image/gif"), "Only JPEG"),
    ((io.BytesIO(b"not a photo"), "room.jpg", "image/jpeg"), "image content is invalid"),
    ((io.BytesIO(b""), "room.jpg", "image/jpeg"), "image file is empty"),
    ((io.BytesIO(b"x" * (MAX_PHOTO_BYTES + 1)), "room.jpg", "image/jpeg"), "5 MB limit"),
    ((io.BytesIO(b"x"), "../room.jpg", "image/jpeg"), "safe filename"),
    ((io.BytesIO(b"x"), "room.jpg", "image/png"), "does not match"),
])
def test_invalid_upload_rejected_without_staging(photo_client, file, error_fragment):
    page = upload(photo_client, step_five(photo_client), file=file)
    assert page.status_code == 422
    assert error_fragment in page.get_data(as_text=True)
    assert staged(photo_client, page) == []


def test_category_limits_are_independent_and_batch_is_atomic(photo_client):
    page = step_five(photo_client)
    for category in PHOTO_CATEGORIES:
        files = [image_file(name=f"{category}-{index}.jpg") for index in range(4)]
        page = post_action(photo_client, page, f"upload_{category}", **{f"photos_{category}": files})
        assert page.status_code == 200
    assert len(staged(photo_client, page)) == 28
    rejected = upload(photo_client, page, file=image_file(name="fifth.jpg"))
    assert rejected.status_code == 422
    assert len(staged(photo_client, rejected)) == 28
    forged = upload(photo_client, page, category="invalid", file=image_file())
    assert forged.status_code == 422
    assert len(staged(photo_client, forged)) == 28


def test_mixed_valid_and_invalid_batch_uploads_nothing(photo_client):
    page = step_five(photo_client)
    batch = [image_file(name="valid.jpg"), (io.BytesIO(b"invalid"), "invalid.jpg", "image/jpeg")]
    rejected = post_action(photo_client, page, "upload_exterior", photos_exterior=batch)
    assert rejected.status_code == 422
    assert staged(photo_client, rejected) == []


def test_delete_primary_and_ordering(photo_client):
    page = step_five(photo_client)
    for index in range(3):
        page = upload(photo_client, page, file=image_file(name=f"photo-{index}.jpg"))
    photos = staged(photo_client, page)
    first, second, third = [photo["id"] for photo in photos]
    page = post_action(photo_client, page, f"primary_{third}")
    assert [photo["id"] for photo in staged(photo_client, page) if photo["is_primary"]] == [third]
    page = post_action(photo_client, page, f"up_{third}")
    order = sorted(staged(photo_client, page), key=lambda photo: photo["display_order"])
    assert [photo["id"] for photo in order] == [first, third, second]
    page = post_action(photo_client, page, f"delete_{third}")
    remaining = staged(photo_client, page)
    assert len(remaining) == 2
    assert [photo["id"] for photo in remaining if photo["is_primary"]] == [first]
    assert [photo["display_order"] for photo in remaining] == [0, 1]
    assert property_count() == 0


def submit_with_photo(photo_client, form_data, availability="available", page=None):
    page = page or upload(photo_client, step_five(photo_client))
    staged_photos = staged(photo_client, page)
    token = FormHTML(page).values["_photo_token"]
    review = post_action(photo_client, page, "switch_en", _step="7")
    html = review.get_data(as_text=True)
    assert 'class="review-photo-row"' in html
    assert "Primary photo" in html
    assert f"/admin/properties/staged-photos/{token}/" in html
    data = FormHTML(review).values | {
        key: value for key, value in form_data.items() if key not in DRAFT_OPTIONAL_TEXT_FIELDS
    } | {"_wizard": "1", "_step": "7", "_action": "submit", "availability_status": availability}
    result = photo_client.post("/admin/properties", data=data, follow_redirects=True)
    assert result.status_code == 200
    assert "Your property has been submitted for review successfully." in result.get_data(as_text=True)
    property = db.session.scalar(select(Property))
    assert property.publication_status == "pending"
    assert property.availability_status == availability
    assert property_count() == 1
    assert db.session.scalar(select(func.count()).select_from(PropertyPhoto)) == len(staged_photos)
    repeated = photo_client.post("/admin/properties", data=data)
    assert repeated.status_code == 409
    assert property_count() == 1
    return property


def admin_token(page):
    return re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)


def test_submission_admin_approval_and_public_gallery(photo_client, form_data):
    property = submit_with_photo(photo_client, form_data)
    photo = property.photos[0]
    assert photo.is_primary
    assert photo.storage_key.startswith(f"properties/{property.id}/")
    assert property.title_en == ""
    assert form_data["title_ar"] not in photo_client.get("/properties").get_data(as_text=True)
    assert photo_client.get(f"/properties/{property.id}").status_code == 404
    assert photo_client.get(f"/properties/photos/{photo.id}").status_code == 404
    queue = photo_client.get("/admin/properties/pending?lang=en")
    assert queue.status_code == 200
    assert form_data["title_ar"] in queue.get_data(as_text=True)
    review = photo_client.get(f"/admin/properties/{property.id}/review?lang=en")
    assert review.status_code == 200
    assert "Approve &amp; Publish" in review.get_data(as_text=True)
    assert f"/admin/property-photos/{photo.id}" in review.get_data(as_text=True)
    assert photo_client.get(f"/admin/property-photos/{photo.id}").status_code == 200
    approved = photo_client.post(f"/admin/properties/{property.id}/approve", data={
        "csrf_token": admin_token(review), "_language": "en",
    }, follow_redirects=True)
    assert approved.status_code == 200
    assert "Property published successfully." in approved.get_data(as_text=True)
    db.session.refresh(property)
    assert property.publication_status == "published"
    assert form_data["title_ar"] not in photo_client.get("/admin/properties/pending").get_data(as_text=True)
    listing = photo_client.get("/properties?lang=en").get_data(as_text=True)
    assert form_data["title_ar"] in listing
    assert f"/properties/photos/{photo.id}" in listing
    details = photo_client.get(f"/properties/{property.id}?lang=en").get_data(as_text=True)
    assert 'class="photo-gallery"' in details
    assert "Primary photo" in details
    assert photo_client.get(f"/properties/photos/{photo.id}").status_code == 200


def test_photo_state_survives_wizard_navigation_and_csrf(photo_client):
    page = upload(photo_client, step_five(photo_client))
    token = FormHTML(page).values["_photo_token"]
    contact = post_action(photo_client, page, "next")
    assert FormHTML(contact).values["_step"] == "6"
    returned = post_action(photo_client, contact, "back")
    assert FormHTML(returned).values["_step"] == "5"
    assert FormHTML(returned).values["_photo_token"] == token
    assert "1 / 4" in returned.get_data(as_text=True)
    invalid = FormHTML(returned).values
    invalid.pop("csrf_token")
    invalid["_action"] = "delete_" + staged(photo_client, returned)[0]["id"]
    assert photo_client.post("/admin/properties", data=invalid).status_code == 400
    assert len(staged(photo_client, returned)) == 1
    assert photo_client.get("/admin/properties/staged-photos/invalid/unknown").status_code == 404


def test_multi_category_gallery_primary_and_empty_categories(photo_client, form_data):
    page = step_five(photo_client)
    for index in range(2):
        page = upload(photo_client, page, "exterior", image_file(name=f"front-{index}.jpg"))
    page = upload(photo_client, page, "kitchen", image_file(name="kitchen.jpg"))
    photos = staged(photo_client, page)
    kitchen = next(photo for photo in photos if photo["category"] == "kitchen")
    exterior = [photo for photo in photos if photo["category"] == "exterior"]
    page = post_action(photo_client, page, f"up_{exterior[1]['id']}")
    page = post_action(photo_client, page, f"primary_{kitchen['id']}")
    property = submit_with_photo(photo_client, form_data, page=page)
    assert len(property.photos) == 3
    assert sum(photo.is_primary for photo in property.photos) == 1
    assert next(photo for photo in property.photos if photo.is_primary).category == "kitchen"
    assert [photo.original_filename for photo in sorted(
        (photo for photo in property.photos if photo.category == "exterior"),
        key=lambda photo: photo.display_order,
    )] == ["front-1.jpg", "front-0.jpg"]
    review = photo_client.get(f"/admin/properties/{property.id}/review")
    photo_client.post(f"/admin/properties/{property.id}/approve", data={
        "csrf_token": admin_token(review),
    })
    listing = photo_client.get("/properties").get_data(as_text=True)
    primary = next(photo for photo in property.photos if photo.is_primary)
    assert f'/properties/photos/{primary.id}' in listing
    english = photo_client.get(f"/properties/{property.id}?lang=en").get_data(as_text=True)
    assert "Kitchen" in english and "Exterior" in english
    assert "<h3>Bathroom</h3>" not in english
    for photo in property.photos:
        assert f"/properties/photos/{photo.id}" in english
    arabic = photo_client.get(f"/properties/{property.id}").get_data(as_text=True)
    assert "المطبخ" in arabic and "الواجهة" in arabic


def test_rented_approval_remains_nonpublic_and_rejection_returns_draft(photo_client, form_data):
    property = submit_with_photo(photo_client, form_data, availability="rented")
    review = photo_client.get(f"/admin/properties/{property.id}/review")
    assert photo_client.post(f"/admin/properties/{property.id}/approve", data={
        "csrf_token": admin_token(review),
    }).status_code == 303
    db.session.refresh(property)
    assert property.publication_status == "published"
    assert property.availability_status == "rented"
    assert photo_client.get(f"/properties/{property.id}").status_code == 404
    assert photo_client.get(f"/properties/photos/{property.photos[0].id}").status_code == 404
    other = Property(**form_data_to_model(form_data), publication_status="pending")
    db.session.add(other)
    db.session.commit()
    review = photo_client.get(f"/admin/properties/{other.id}/review")
    rejected = photo_client.post(f"/admin/properties/{other.id}/reject", data={
        "csrf_token": admin_token(review),
    }, follow_redirects=True)
    assert rejected.status_code == 200
    assert other.publication_status == "draft"
    assert photo_client.get(f"/properties/{other.id}").status_code == 404


def form_data_to_model(form_data):
    from decimal import Decimal
    return {
        key: form_data[key] for key in (
            "title_en", "title_ar", "description_en", "description_ar",
            "state_en", "state_ar", "city_en", "city_ar", "area_en", "area_ar",
            "property_type", "currency", "contact_name", "phone", "contact_role",
        )
    } | {"monthly_rent": Decimal(form_data["monthly_rent"]),
         "bedrooms": int(form_data["bedrooms"]), "bathrooms": int(form_data["bathrooms"])}


def test_admin_approval_requires_csrf(photo_client, values):
    property = Property(**values, publication_status="pending")
    db.session.add(property)
    db.session.commit()
    response = photo_client.post(f"/admin/properties/{property.id}/approve")
    assert response.status_code == 400
    db.session.refresh(property)
    assert property.publication_status == "pending"
