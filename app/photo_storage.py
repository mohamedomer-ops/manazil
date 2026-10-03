"""Validated property photos with interchangeable local and private-blob storage."""
import io
import json
import re
import shutil
import warnings
from pathlib import Path
from uuid import uuid4

from flask import current_app, send_file
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image, ImageOps, UnidentifiedImageError

from app.models import PHOTO_CATEGORIES


MAX_PHOTOS_PER_PROPERTY = 20
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
FORMATS = {
    ".jpg": ("JPEG", "image/jpeg", "jpg"),
    ".jpeg": ("JPEG", "image/jpeg", "jpg"),
    ".png": ("PNG", "image/png", "png"),
    ".webp": ("WEBP", "image/webp", "webp"),
}
KEY_PATTERN = re.compile(r"(?:staging/[0-9a-f]{32}|properties/[0-9]+)/[0-9a-f]{32}\.(?:jpg|png|webp)\Z|avatars/[0-9]+/[0-9a-f]{32}\.webp\Z")
AVATAR_KEY_PATTERN = re.compile(r"avatars/[0-9]+/[0-9a-f]{32}\.webp\Z")


class PhotoError(ValueError):
    pass


def category_label(category, language):
    names = {
        "exterior": ("Exterior", "الواجهة"),
        "entrance": ("Entrance", "المدخل"),
        "living_room": ("Living Room", "غرفة المعيشة"),
        "bedroom": ("Bedroom", "غرفة النوم"),
        "kitchen": ("Kitchen", "المطبخ"),
        "bathroom": ("Bathroom", "الحمام"),
        "other": ("Other", "أخرى"),
    }
    pair = names.get(category)
    return pair[1 if language == "ar" else 0] if pair else category


def validate_image(upload):
    filename = (upload.filename or "").strip()
    if (
        not filename or len(filename) > 255 or filename.startswith(".") or ".." in filename
        or any(not (char.isalnum() or char in "._- ") for char in filename)
    ):
        raise PhotoError("Choose a file with a safe filename.")
    extension = Path(filename).suffix.lower()
    expected = FORMATS.get(extension)
    if expected is None:
        raise PhotoError("Only JPEG, PNG, and WebP images are allowed.")
    image_format, content_type, output_extension = expected
    if upload.mimetype != content_type:
        raise PhotoError("The image type does not match its filename.")
    payload = upload.stream.read(MAX_PHOTO_BYTES + 1)
    if not payload:
        raise PhotoError("The image file is empty.")
    if len(payload) > MAX_PHOTO_BYTES:
        raise PhotoError("The image exceeds the 5 MB limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                if image.format != image_format or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise PhotoError("The image content is invalid.")
                image.verify()
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                clean = ImageOps.exif_transpose(image)
                if image_format == "JPEG":
                    clean = clean.convert("RGB")
                output = io.BytesIO()
                clean.save(output, format=image_format)
                image_bytes = output.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise PhotoError("The image content is invalid.") from error
    if not image_bytes or len(image_bytes) > MAX_PHOTO_BYTES:
        raise PhotoError("The image exceeds the 5 MB limit.")
    return filename, content_type, output_extension, image_bytes


class LocalPhotoStorage:
    """The adapter owns all filesystem paths; routes handle only opaque IDs."""

    def __init__(self):
        self.root = Path(current_app.config["PHOTO_STORAGE_ROOT"]).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _signer():
        return URLSafeTimedSerializer(current_app.secret_key, salt="manazil-photo-wizard")

    def new_token(self):
        return self._signer().dumps(uuid4().hex)

    def draft_id(self, token):
        try:
            value = self._signer().loads(token, max_age=24 * 60 * 60)
        except (BadSignature, SignatureExpired, TypeError) as error:
            raise PhotoError("The photo session is invalid or expired.") from error
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
            raise PhotoError("The photo session is invalid or expired.")
        return value

    def _draft_dir(self, draft_id):
        return self.root / "staging" / draft_id

    def path(self, storage_key):
        if not isinstance(storage_key, str) or not KEY_PATTERN.fullmatch(storage_key):
            raise PhotoError("The photo reference is invalid.")
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root):
            raise PhotoError("The photo reference is invalid.")
        return path

    def _read_manifest(self, draft_id):
        manifest = self._draft_dir(draft_id) / "manifest.json"
        return manifest.read_bytes() if manifest.exists() else None

    def _write_manifest(self, draft_id, payload):
        directory = self._draft_dir(draft_id)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".{uuid4().hex}.json"
        temporary.write_bytes(payload)
        temporary.replace(directory / "manifest.json")

    def _save_image(self, key, payload, content_type):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as file:
            file.write(payload)

    def _delete_image(self, key):
        self.path(key).unlink(missing_ok=True)

    def _exists_image(self, key):
        return self.path(key).is_file()

    def _copy_image(self, source, destination, content_type):
        target = self.path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path(source), target)

    def send(self, key, mimetype, *, max_age=None):
        return send_file(self.path(key), mimetype=mimetype, max_age=max_age)

    def save_avatar(self, user_id, payload):
        key = f"avatars/{user_id}/{uuid4().hex}.webp"
        if type(user_id) is not int or user_id < 1 or not payload:
            raise PhotoError('The avatar is invalid.')
        try:
            self._save_image(key, payload, 'image/webp')
        except Exception:
            try:
                self._delete_image(key)
            except (PhotoError, OSError):
                pass
            raise
        return key

    @staticmethod
    def _validate_avatar_key(key, user_id):
        if (type(user_id) is not int or user_id < 1 or not isinstance(key, str) or
                not AVATAR_KEY_PATTERN.fullmatch(key) or not key.startswith(f'avatars/{user_id}/')):
            raise PhotoError('The avatar reference is invalid.')

    def delete_avatar(self, key, user_id):
        self._validate_avatar_key(key, user_id)
        self._delete_image(key)

    def send_avatar(self, key, user_id):
        self._validate_avatar_key(key, user_id)
        return self.send(key, 'image/webp', max_age=0)

    def read(self, token):
        draft_id = self.draft_id(token)
        try:
            manifest = self._read_manifest(draft_id)
        except OSError as error:
            raise PhotoError("The photo session could not be read.") from error
        if manifest is None:
            return {"photos": [], "submitted_property_id": None}
        try:
            data = json.loads(manifest)
            if not isinstance(data["photos"], list):
                raise ValueError
            return data
        except (OSError, ValueError, KeyError) as error:
            raise PhotoError("The photo session could not be read.") from error

    def _write(self, token, data):
        self._write_manifest(self.draft_id(token), json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def add(self, token, category, uploads, *, max_photos=MAX_PHOTOS_PER_PROPERTY, auto_primary=True):
        if category not in PHOTO_CATEGORIES:
            raise PhotoError("Choose a valid photo category.")
        data = self.read(token)
        if data.get("submitted_property_id"):
            raise PhotoError("This property has already been submitted.")
        if not uploads:
            raise PhotoError("Choose at least one photo.")
        current = list(data["photos"])
        if len(current) + len(uploads) > max_photos:
            raise PhotoError("A property can contain at most 20 photos.")
        checked = [validate_image(upload) for upload in uploads]
        written = []
        try:
            for filename, content_type, extension, image_bytes in checked:
                photo_id = uuid4().hex
                key = f"staging/{self.draft_id(token)}/{photo_id}.{extension}"
                self._save_image(key, image_bytes, content_type)
                written.append(key)
                data["photos"].append({
                    "id": photo_id, "category": category, "storage_key": key,
                    "original_filename": filename, "content_type": content_type,
                    "file_size": len(image_bytes), "display_order": len(current),
                    "is_primary": auto_primary and not any(photo["is_primary"] for photo in data["photos"]),
                })
                current.append(data["photos"][-1])
            self._write(token, data)
        except Exception:
            self.remove_keys(written)
            raise
        return data["photos"]

    def change(self, token, photo_id, action):
        if not re.fullmatch(r"[0-9a-f]{32}", photo_id):
            raise PhotoError("Choose a valid photo.")
        data = self.read(token)
        if data.get("submitted_property_id"):
            raise PhotoError("This property has already been submitted.")
        photos = data["photos"]
        selected = next((photo for photo in photos if photo["id"] == photo_id), None)
        if selected is None:
            raise PhotoError("Choose a valid photo.")
        if action == "delete":
            photos.remove(selected)
            for index, photo in enumerate(sorted(photos, key=lambda item: item["display_order"])):
                photo["display_order"] = index
            if selected["is_primary"] and photos:
                photos[0]["is_primary"] = True
            self._write(token, data)
            self._delete_image(selected["storage_key"])
        elif action == "primary":
            for photo in photos:
                photo["is_primary"] = photo["id"] == photo_id
            self._write(token, data)
        elif action in ("up", "down"):
            siblings = sorted(photos, key=lambda photo: photo["display_order"])
            index = siblings.index(selected)
            destination = index + (-1 if action == "up" else 1)
            if 0 <= destination < len(siblings):
                other = siblings[destination]
                selected["display_order"], other["display_order"] = other["display_order"], selected["display_order"]
                self._write(token, data)
        else:
            raise PhotoError("Choose a valid photo action.")
        return photos

    def clear_primary(self, token):
        data = self.read(token)
        if data.get("submitted_property_id"):
            raise PhotoError("This property has already been submitted.")
        for photo in data["photos"]:
            photo["is_primary"] = False
        self._write(token, data)

    def prepare_property_photos(self, token, property_id):
        photos = self.read(token)["photos"]
        if len(photos) > MAX_PHOTOS_PER_PROPERTY:
            raise PhotoError("A property can contain at most 20 photos.")
        prepared = []
        copied = []
        try:
            for photo in photos:
                source = photo["storage_key"]
                if not self._exists_image(source):
                    raise PhotoError("An uploaded photo is missing. Please upload it again.")
                extension = Path(source).suffix
                key = f"properties/{property_id}/{photo['id']}{extension}"
                copied.append(key)
                self._copy_image(source, key, photo['content_type'])
                prepared.append(photo | {"storage_key": key})
        except Exception:
            self.remove_keys(copied)
            raise
        return prepared, copied

    def remove_keys(self, keys):
        for key in keys:
            self._delete_image(key)

    def mark_submitted(self, token, property_id):
        data = self.read(token)
        staged = list(data["photos"])
        data["photos"] = []
        data["submitted_property_id"] = property_id
        self._write(token, data)
        for photo in staged:
            self._delete_image(photo["storage_key"])


def photo_storage():
    backend = current_app.config['PHOTO_STORAGE_BACKEND']
    if backend == 'local':
        return LocalPhotoStorage()
    if backend == 'azure_blob':
        from app.azure_photo_storage import AzureBlobPhotoStorage
        return AzureBlobPhotoStorage()
    raise PhotoError('Photo storage is unavailable.')
