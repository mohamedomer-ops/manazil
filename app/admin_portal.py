"""Staff-only marketplace operations. Owner posting remains in app.admin."""
from functools import wraps
import re

import click
from flask import Blueprint, abort, g, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import selectinload

from app import db
from app.auth import establish_session
from app.languages import current_language, format_rent
from app.models import Property, PropertyPhoto, User, utc_now
from app.otp import request_code, verify_code
from app.phone import normalize_phone, property_contact_number
from app.photo_storage import LocalPhotoStorage, PhotoError
from app.property_filters import STATE_OPTIONS

portal = Blueprint('admin_portal', __name__, url_prefix='/admin')
PAGE_SIZE = 25


def admin_destination(value):
    from urllib.parse import urlsplit
    parsed = urlsplit(value or '')
    allowed_path = (parsed.path in ('/admin', '/admin/properties', '/admin/users', '/admin/reports', '/admin/admins') or
                    re.fullmatch(r'/admin/(?:properties|users)/[1-9][0-9]*', parsed.path))
    if allowed_path and not parsed.scheme and not parsed.netloc and not (value or '').startswith('//') and '\\' not in (value or '') and not any(ord(c) < 32 for c in (value or '')):
        return value
    return url_for('admin_portal.dashboard')


def admin_required(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        user = g.get('user')
        if user is None:
            destination = request.full_path if request.query_string else request.path
            return redirect(url_for('admin_portal.login', next=admin_destination(destination)))
        if user.role != 'admin':
            abort(403)
        if not session.get('admin_authenticated'):
            destination = request.full_path if request.query_string else request.path
            return redirect(url_for('admin_portal.login', next=admin_destination(destination)))
        return view(*args, **kwargs)
    return guarded


@portal.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@portal.errorhandler(403)
def access_denied(error):
    return render_template('administration/forbidden.html'), 403


@portal.get('/login')
def login():
    return render_template('administration/login.html', next=admin_destination(request.args.get('next')))


@portal.post('/login')
def login_post():
    destination = admin_destination(request.form.get('next'))
    try:
        phone = normalize_phone(request.form.get('phone_number'))
    except ValueError:
        return render_template('administration/login.html', next=destination, error='Enter a valid phone number.'), 422
    # Give no account/role information before the OTP is proven.
    user = db.session.scalar(select(User).where(User.phone_number == phone))
    if user and user.is_active and user.is_verified:
        request_code(phone)
    session['admin_phone'] = phone
    session['admin_next'] = destination
    return redirect(url_for('admin_portal.verify', **({'lang': 'en'} if current_language() == 'en' else {})), code=303)


@portal.get('/verify')
def verify():
    if not session.get('admin_phone'):
        return redirect(url_for('admin_portal.login'))
    return render_template('administration/verify.html')


@portal.post('/verify')
def verify_post():
    phone = session.get('admin_phone')
    if not phone or not verify_code(phone, request.form.get('code')):
        return render_template('administration/verify.html', error='Invalid or expired verification code.'), 422
    session.pop('admin_phone', None)
    user = db.session.scalar(select(User).where(User.phone_number == phone))
    if not user or not user.is_active or user.role != 'admin':
        session.pop('admin_next', None)
        abort(403)
    user.last_login_at = utc_now()
    db.session.commit()
    destination = admin_destination(session.pop('admin_next', None))
    response = establish_session(user, destination)
    session['admin_authenticated'] = True
    return response


@portal.post('/resend')
def resend():
    phone = session.get('admin_phone')
    if not phone:
        return redirect(url_for('admin_portal.login'), code=303)
    user = db.session.scalar(select(User).where(User.phone_number == phone))
    if user and user.is_active and user.is_verified:
        request_code(phone)
    return redirect(url_for('admin_portal.verify', **({'lang': 'en'} if current_language() == 'en' else {})), code=303)


@portal.post('/logout')
@admin_required
def logout():
    csrf_value = session.get('csrf_token')
    session.clear()
    if csrf_value:
        session['csrf_token'] = csrf_value
    return redirect(url_for('admin_portal.login'), code=303)


def count(model, *conditions):
    return db.session.scalar(select(func.count()).select_from(model).where(*conditions))


@portal.get('/')
@portal.get('')
@admin_required
def dashboard():
    stats = {
        'Total Properties': count(Property), 'Published Properties': count(Property, Property.publication_status == 'published'),
        'Available Properties': count(Property, Property.availability_status == 'available'),
        'Rented Properties': count(Property, Property.availability_status == 'rented'),
        'Properties for Rent': count(Property, Property.transaction_type == 'rent'),
        'Properties for Sale': count(Property, Property.transaction_type == 'sale'),
        'Total Registered Users': count(User), 'Owner listings': count(Property, Property.contact_role == 'owner'),
        'Broker listings': count(Property, Property.contact_role == 'broker'),
        'Properties with photos': count(Property, Property.photos.any()),
        'Properties without photos': count(Property, ~Property.photos.any()),
    }
    recent_properties = db.session.scalars(select(Property).order_by(Property.created_at.desc(), Property.id.desc()).limit(10)).all()
    recent_users = db.session.scalars(select(User).order_by(User.created_at.desc(), User.id.desc()).limit(10)).all()
    return render_template('administration/dashboard.html', stats=stats, recent_properties=recent_properties,
                           recent_users=recent_users, format_rent=format_rent)


def page_number():
    try:
        return max(1, min(int(request.args.get('page', '1')), 100000))
    except ValueError:
        return 1


@portal.get('/properties')
@admin_required
def properties():
    first_photo = (select(PropertyPhoto.id).where(PropertyPhoto.property_id == Property.id)
                   .order_by(PropertyPhoto.is_primary.desc(), PropertyPhoto.display_order, PropertyPhoto.id)
                   .limit(1).scalar_subquery())
    query = select(Property, first_photo)
    search = request.args.get('search', '').strip()[:100]
    if search:
        conditions = [Property.title_ar.ilike(f'%{search}%'), Property.title_en.ilike(f'%{search}%')]
        if search.isdigit():
            conditions.append(Property.id == int(search))
        query = query.where(or_(*conditions))
    for field, allowed in (('transaction_type', ('rent', 'sale')), ('publication_status', ('draft', 'published')),
                           ('availability_status', ('available', 'rented')), ('contact_role', ('owner', 'broker')),
                           ('moderation_status', ('clear', 'disabled'))):
        value = request.args.get(field)
        if value in allowed:
            query = query.where(getattr(Property, field) == value)
    state = request.args.get('state')
    state_match = next((name for slug, name, _ in STATE_OPTIONS if slug == state), None)
    if state_match:
        query = query.where(Property.state_en == state_match)
    page = page_number()
    listings = db.session.execute(query.order_by(Property.created_at.desc(), Property.id.desc())
                                  .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)).all()
    return render_template('administration/properties.html', properties=listings, states=STATE_OPTIONS,
                           page=page, has_next=len(listings) == PAGE_SIZE, format_rent=format_rent)


@portal.get('/properties/<int:property_id>')
@admin_required
def property_detail(property_id):
    property = db.session.scalar(select(Property).options(selectinload(Property.photos)).where(Property.id == property_id))
    if property is None:
        abort(404)
    return render_template('administration/property_detail.html', property=property,
                           contact_number=property_contact_number(property), format_rent=format_rent)


@portal.get('/photos/<int:photo_id>')
@admin_required
def photo(photo_id):
    item = db.session.get(PropertyPhoto, photo_id)
    if item is None:
        abort(404)
    try:
        return send_file(LocalPhotoStorage().path(item.storage_key), mimetype=item.content_type, max_age=0)
    except (PhotoError, OSError):
        abort(404)


@portal.post('/properties/<int:property_id>/moderate')
@admin_required
def moderate_property(property_id):
    property = db.session.get(Property, property_id)
    if property is None:
        abort(404)
    action = request.form.get('action')
    if action not in ('disable', 'restore'):
        abort(400)
    property.moderation_status = 'disabled' if action == 'disable' else 'clear'
    db.session.commit()
    return redirect(url_for('admin_portal.property_detail', property_id=property_id), code=303)


@portal.get('/users')
@admin_required
def users():
    property_counts = (select(Property.owner_id, func.count(Property.id).label('total'))
                       .group_by(Property.owner_id).subquery())
    query = select(User, func.coalesce(property_counts.c.total, 0)).outerjoin(
        property_counts, property_counts.c.owner_id == User.id)
    search = request.args.get('search', '').strip()[:100]
    if search:
        conditions = [User.contact_name.ilike(f'%{search}%'), User.phone_number.ilike(f'%{search}%')]
        if search.isdigit():
            conditions.append(User.id == int(search))
        query = query.where(or_(*conditions))
    status = request.args.get('status')
    if status in ('active', 'suspended'):
        query = query.where(User.is_active.is_(status == 'active'))
    role = request.args.get('role')
    if role in ('user', 'admin'):
        query = query.where(User.role == role)
    page = page_number()
    people = db.session.execute(query.order_by(User.created_at.desc(), User.id.desc())
                                .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)).all()
    return render_template('administration/users.html', users=people, page=page, has_next=len(people) == PAGE_SIZE)


@portal.get('/users/<int:user_id>')
@admin_required
def user_detail(user_id):
    user = db.session.scalar(select(User).options(selectinload(User.properties), selectinload(User.identities)).where(User.id == user_id))
    if user is None:
        abort(404)
    return render_template('administration/user_detail.html', user=user)


def remaining_active_admins(target):
    return count(User, User.role == 'admin', User.is_active.is_(True), User.id != target.id)


@portal.post('/users/<int:user_id>/status')
@admin_required
def user_status(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    action = request.form.get('action')
    if action not in ('suspend', 'reactivate'):
        abort(400)
    if action == 'suspend' and target.role == 'admin' and (target.id == g.user.id or not remaining_active_admins(target)):
        abort(409)
    target.is_active = action == 'reactivate'
    db.session.commit()
    return redirect(url_for('admin_portal.user_detail', user_id=user_id), code=303)


@portal.get('/admins')
@admin_required
def admins():
    administrators = db.session.scalars(select(User).where(User.role == 'admin').order_by(User.id)).all()
    return render_template('administration/admins.html', administrators=administrators)


@portal.post('/admins/promote')
@admin_required
def promote_user():
    try:
        user_id = int(request.form.get('user_id', ''))
    except ValueError:
        abort(400)
    return set_role(user_id, 'promote')


@portal.post('/admins/<int:user_id>/role')
@admin_required
def change_role(user_id):
    return set_role(user_id, request.form.get('action'))


def set_role(user_id, action):
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    if action not in ('promote', 'revoke'):
        abort(400)
    if action == 'promote' and (not target.is_active or not target.is_verified or not target.phone_number):
        abort(409)
    if action == 'revoke' and target.role == 'admin' and (target.id == g.user.id or not remaining_active_admins(target)):
        abort(409)
    target.role = 'admin' if action == 'promote' else 'user'
    db.session.commit()
    return redirect(url_for('admin_portal.admins'), code=303)


@portal.get('/reports')
@admin_required
def reports():
    groups = {}
    for title, column in (('Properties by State', Property.state_en), ('Rent vs Sale', Property.transaction_type),
                          ('Available vs Rented', Property.availability_status), ('Owner vs Broker', Property.contact_role),
                          ('Publication Status', Property.publication_status)):
        groups[title] = db.session.execute(select(column, func.count(Property.id)).group_by(column).order_by(column)).all()
    property_month = func.date_trunc(literal_column("'month'"), Property.created_at)
    user_month = func.date_trunc(literal_column("'month'"), User.created_at)
    property_months = db.session.execute(select(property_month, func.count(Property.id))
                                         .group_by(property_month).order_by(property_month.desc()).limit(12)).all()
    user_months = db.session.execute(select(user_month, func.count(User.id))
                                     .group_by(user_month).order_by(user_month.desc()).limit(12)).all()
    return render_template('administration/reports.html', groups=groups, total_users=count(User),
                           total_properties=count(Property), property_months=property_months, user_months=user_months,
                           state_names={english: arabic for _, english, arabic in STATE_OPTIONS})


def register_cli(app):
    for command_name, role in (('grant-admin', 'admin'), ('revoke-admin', 'user')):
        @app.cli.command(command_name)
        @click.argument('phone')
        def change_admin_cli(phone, target_role=role):
            try:
                normalized = normalize_phone(phone)
            except ValueError:
                raise click.ClickException('Enter a valid phone number.') from None
            target = db.session.scalar(select(User).where(User.phone_number == normalized))
            if target is None:
                raise click.ClickException('Existing user not found.')
            if target_role == 'admin' and (not target.is_active or not target.is_verified):
                raise click.ClickException('Administrator accounts require an active, verified phone login.')
            if target_role == 'user' and target.role == 'admin' and not remaining_active_admins(target):
                raise click.ClickException('Cannot revoke the final active administrator.')
            target.role = target_role
            db.session.commit()
            click.echo(f'User {target.id} role is now {target_role}.')
