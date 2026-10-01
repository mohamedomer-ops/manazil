"""Account-owned bookmarks; saving never grants access to private listings."""
from flask import Blueprint, abort, current_app, g, redirect, render_template, request, url_for
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.auth import login_required
from app.languages import availability_label, current_language, format_rent, property_type_label
from app.models import Property, SavedProperty
from app.property_forms import sudan_today

saved = Blueprint('saved', __name__)


@saved.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def detail_destination(property_id):
    return url_for('main.property_detail', property_id=property_id,
                   **({'lang': 'en'} if current_language() == 'en' else {}))


@saved.get('/saved-properties')
@login_required
def saved_properties():
    ids = db.session.scalars(select(SavedProperty.property_id).where(
        SavedProperty.user_id == g.user.id).order_by(SavedProperty.created_at.desc(), SavedProperty.property_id.desc())).all()
    # Only load card details for properties that are still publicly accessible.
    public = db.session.scalars(select(Property).options(selectinload(Property.photos)).where(
        Property.id.in_(ids), Property.publication_status == 'published', Property.availability_status == 'available')).all() if ids else []
    by_id = {property.id: property for property in public}
    entries = [{'property_id': property_id, 'property': by_id.get(property_id)} for property_id in ids]
    return render_template('saved_properties.html', entries=entries, today=sudan_today(),
                           availability_label=availability_label, format_rent=format_rent,
                           property_type_label=property_type_label)


@saved.post('/properties/<int:property_id>/save')
def save_property(property_id):
    # Return to the detail page, never to this POST-only endpoint, after authentication.
    if g.get('user') is None:
        return redirect(url_for('auth.entry', next=detail_destination(property_id),
                                **({'lang': 'en'} if current_language() == 'en' else {})), code=303)
    property = db.session.scalar(select(Property.id).where(
        Property.id == property_id, Property.publication_status == 'published', Property.availability_status == 'available'))
    if property is None:
        abort(404)
    try:
        db.session.execute(insert(SavedProperty).values(user_id=g.user.id, property_id=property_id)
                           .on_conflict_do_nothing(index_elements=['user_id', 'property_id']))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Saving property failed.')
        abort(503)
    return redirect(detail_destination(property_id), code=303)


@saved.post('/properties/<int:property_id>/unsave')
@login_required
def unsave_property(property_id):
    try:
        db.session.execute(delete(SavedProperty).where(SavedProperty.user_id == g.user.id,
                                                      SavedProperty.property_id == property_id))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Removing saved property failed.')
        abort(503)
    # Destinations are chosen server-side rather than accepting arbitrary redirects.
    if request.form.get('return_to') == 'detail':
        return redirect(detail_destination(property_id), code=303)
    return redirect(url_for('saved.saved_properties', **({'lang': 'en'} if current_language() == 'en' else {})), code=303)
