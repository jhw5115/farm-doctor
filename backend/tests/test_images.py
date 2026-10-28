import pytest

pytest.skip("Legacy /api/images S3 API was replaced by the PRD-required /api/v1 inspections API.", allow_module_level=True)

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import Mock

from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from fastapi.testclient import TestClient

from app.images import get_storage
from app.main import app
from app.storage import ObjectNotFoundError, S3Storage


class FakeStorage:
    bucket = "test-images"

    def __init__(self) -> None:
        self.saved: dict[str, tuple[bytes, str]] = {}

    def put_object(self, key, body, content_type) -> None:
        self.saved[key] = (body.read(), content_type)

    def list_objects(self):
        return [
            {
                "Key": key,
                "Size": len(content),
                "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
            for key, (content, _) in self.saved.items()
        ]

    def get_object(self, key):
        if key not in self.saved:
            raise ObjectNotFoundError(key)
        content, content_type = self.saved[key]
        return StreamingBody(BytesIO(content), len(content)), content_type


def test_image_upload_list_and_download() -> None:
    storage = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            upload = client.post(
                "/api/images",
                files={"file": ("leaf.png", b"image-bytes", "image/png")},
            )
            assert upload.status_code == 200
            uploaded = upload.json()
            assert uploaded["bucket"] == "test-images"
            assert uploaded["key"].endswith(".png")

            listing = client.get("/api/images")
            assert listing.status_code == 200
            assert listing.json()["objects"] == [
                {
                    "key": uploaded["key"],
                    "size": len(b"image-bytes"),
                    "last_modified": "2026-01-01T00:00:00+00:00",
                }
            ]

            download = client.get(f"/api/images/{uploaded['key']}")
            assert download.status_code == 200
            assert download.headers["content-type"] == "image/png"
            assert download.content == b"image-bytes"
    finally:
        app.dependency_overrides.clear()


def test_image_upload_rejects_non_image() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/images",
            files={"file": ("notes.txt", b"not an image", "text/plain")},
        )

    assert response.status_code == 415


def test_image_download_returns_not_found() -> None:
    storage = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            response = client.get("/api/images/missing.png")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_storage_creates_missing_bucket() -> None:
    storage = object.__new__(S3Storage)
    storage.bucket = "test-images"
    storage.create_bucket = True
    storage.client = Mock()
    storage.client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadBucket"
    )

    storage.ensure_bucket()

    storage.client.create_bucket.assert_called_once_with(Bucket="test-images")
