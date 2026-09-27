"""Validated image storage behind a small local-filesystem adapter."""
import io
import json
import re
import shutil
import warnings
from pathlib import Path
from uuid import uuid4

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image, ImageOps, UnidentifiedImageError

from app.models import PHOTO_CATEGORIES


MAX_PHOTOS_PER_CATEGORY = 4
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
FORMATS = {
    ".jpg": ("JPEG", "image/jpeg", "jpg"),
    ".jpeg": ("JPEG", "image/jpeg", "jpg"),
    ".png": ("PNG", "image/png", "png"),
    ".webp": ("WEBP", "image/webp", "webp"),
}
KEY_PATTERN = re.compile(r"(?:staging/[0-9a-f]{32}|properties/[0-9]+)/[0-9a-f]{32}\.(?:jpg|png|webp)\Z")


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

    def read(self, token):
        draft_id = self.draft_id(token)
        manifest = self._draft_dir(draft_id) / "manifest.json"
        if not manifest.exists():
            return {"photos": [], "submitted_property_id": None}
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data["photos"], list):
                raise ValueError
            return data
        except (OSError, ValueError, KeyError) as error:
            raise PhotoError("The photo session could not be read.") from error

    def _write(self, token, data):
        directory = self._draft_dir(self.draft_id(token))
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".{uuid4().hex}.json"
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(directory / "manifest.json")

    def add(self, token, category, uploads):
        if category not in PHOTO_CATEGORIES:
            raise PhotoError("Choose a valid photo category.")
        data = self.read(token)
        if data.get("submitted_property_id"):
            raise PhotoError("This property has already been submitted.")
        if not uploads:
            raise PhotoError("Choose at least one photo.")
        current = [photo for photo in data["photos"] if photo["category"] == category]
        if len(current) + len(uploads) > MAX_PHOTOS_PER_CATEGORY:
            raise PhotoError("A category can contain at most 4 photos.")
        checked = [validate_image(upload) for upload in uploads]
        written = []
        try:
            for filename, content_type, extension, image_bytes in checked:
                photo_id = uuid4().hex
                key = f"staging/{self.draft_id(token)}/{photo_id}.{extension}"
                path = self.path(key)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as file:
                    file.write(image_bytes)
                written.append(path)
                data["photos"].append({
                    "id": photo_id, "category": category, "storage_key": key,
                    "original_filename": filename, "content_type": content_type,
                    "file_size": len(image_bytes), "display_order": len(current),
                    "is_primary": not any(photo["is_primary"] for photo in data["photos"]),
                })
                current.append(data["photos"][-1])
            self._write(token, data)
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
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
            category_photos = [photo for photo in photos if photo["category"] == selected["category"]]
            for index, photo in enumerate(category_photos):
                photo["display_order"] = index
            if selected["is_primary"] and photos:
                photos[0]["is_primary"] = True
            self._write(token, data)
            self.path(selected["storage_key"]).unlink(missing_ok=True)
        elif action == "primary":
            for photo in photos:
                photo["is_primary"] = photo["id"] == photo_id
            self._write(token, data)
        elif action in ("up", "down"):
            siblings = sorted((photo for photo in photos if photo["category"] == selected["category"]), key=lambda photo: photo["display_order"])
            index = siblings.index(selected)
            destination = index + (-1 if action == "up" else 1)
            if 0 <= destination < len(siblings):
                other = siblings[destination]
                selected["display_order"], other["display_order"] = other["display_order"], selected["display_order"]
                self._write(token, data)
        else:
            raise PhotoError("Choose a valid photo action.")
        return photos

    def prepare_property_photos(self, token, property_id):
        photos = self.read(token)["photos"]
        prepared = []
        copied = []
        try:
            for photo in photos:
                source = self.path(photo["storage_key"])
                if not source.is_file():
                    raise PhotoError("An uploaded photo is missing. Please upload it again.")
                extension = source.suffix
                key = f"properties/{property_id}/{photo['id']}{extension}"
                destination = self.path(key)
                destination.parent.mkdir(parents=True, exist_ok=True)
                copied.append(key)
                shutil.copyfile(source, destination)
                prepared.append(photo | {"storage_key": key})
        except Exception:
            self.remove_keys(copied)
            raise
        return prepared, copied

    def remove_keys(self, keys):
        for key in keys:
            self.path(key).unlink(missing_ok=True)

    def mark_submitted(self, token, property_id):
        data = self.read(token)
        staged = list(data["photos"])
        data["photos"] = []
        data["submitted_property_id"] = property_id
        self._write(token, data)
        for photo in staged:
            self.path(photo["storage_key"]).unlink(missing_ok=True)
