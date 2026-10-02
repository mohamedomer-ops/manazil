"""Private Azure Blob implementation of the existing property-photo key contract."""
import io
import re

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings
from flask import current_app, send_file

from app.photo_storage import KEY_PATTERN, MAX_PHOTO_BYTES, LocalPhotoStorage, PhotoError

MANIFEST_PATTERN = re.compile(r'staging/[0-9a-f]{32}/manifest\.json\Z')


class AzureBlobPhotoStorage(LocalPhotoStorage):
    """Keep staging manifests and images in one private container across workers."""

    def __init__(self, container_client=None):
        if container_client is None:
            container_client = current_app.config.get('AZURE_BLOB_CONTAINER_CLIENT')
        if container_client is None:
            try:
                service = BlobServiceClient.from_connection_string(
                    current_app.config['AZURE_STORAGE_CONNECTION_STRING'])
                container_client = service.get_container_client(current_app.config['AZURE_STORAGE_CONTAINER'])
            except (AzureError, ValueError, TypeError) as error:
                raise PhotoError('Photo storage is unavailable.') from error
        self.container = container_client

    def _blob(self, key):
        if not isinstance(key, str) or not (KEY_PATTERN.fullmatch(key) or MANIFEST_PATTERN.fullmatch(key)):
            raise PhotoError('The photo reference is invalid.')
        return self.container.get_blob_client(key)

    def _read_manifest(self, draft_id):
        try:
            blob = self._blob(f'staging/{draft_id}/manifest.json')
            if blob.get_blob_properties().size > 64 * 1024:
                raise PhotoError('The photo session could not be read.')
            payload = blob.download_blob(offset=0, length=64 * 1024 + 1).readall()
            if len(payload) > 64 * 1024:
                raise PhotoError('The photo session could not be read.')
            return payload
        except ResourceNotFoundError:
            return None
        except AzureError as error:
            raise PhotoError('The photo session could not be read.') from error

    def _write_manifest(self, draft_id, payload):
        try:
            self._blob(f'staging/{draft_id}/manifest.json').upload_blob(
                payload, overwrite=True, content_settings=ContentSettings(content_type='application/json'))
        except AzureError as error:
            raise PhotoError('Photo storage is unavailable.') from error

    def _save_image(self, key, payload, content_type):
        try:
            self._blob(key).upload_blob(payload, overwrite=False,
                                        content_settings=ContentSettings(content_type=content_type))
        except AzureError as error:
            raise PhotoError('Photo storage is unavailable.') from error

    def _download_image(self, key):
        try:
            blob = self._blob(key)
            if blob.get_blob_properties().size > MAX_PHOTO_BYTES:
                raise PhotoError('The image exceeds the 5 MB limit.')
            payload = blob.download_blob(offset=0, length=MAX_PHOTO_BYTES + 1).readall()
            if len(payload) > MAX_PHOTO_BYTES:
                raise PhotoError('The image exceeds the 5 MB limit.')
            return payload
        except ResourceNotFoundError as error:
            raise PhotoError('An uploaded photo is missing. Please upload it again.') from error
        except AzureError as error:
            raise PhotoError('Photo storage is unavailable.') from error

    def _delete_image(self, key):
        try:
            self._blob(key).delete_blob(delete_snapshots='include')
        except ResourceNotFoundError:
            pass
        except AzureError as error:
            raise PhotoError('Photo storage is unavailable.') from error

    def _exists_image(self, key):
        try:
            return self._blob(key).exists()
        except AzureError as error:
            raise PhotoError('Photo storage is unavailable.') from error

    def _copy_image(self, source, destination, content_type):
        self._save_image(destination, self._download_image(source), content_type)

    def send(self, key, mimetype, *, max_age=None):
        # The container stays private; existing Flask routes enforce public/owner/admin visibility.
        return send_file(io.BytesIO(self._download_image(key)), mimetype=mimetype, max_age=max_age)
