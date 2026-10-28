import os
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config

from app.config import settings


class Storage:
    def __init__(self) -> None:
        self.is_s3 = settings.storage_backend == "s3"
        if self.is_s3:
            if not settings.s3_bucket:
                raise RuntimeError("S3 저장소 사용 시 S3_BUCKET이 필요합니다.")
            self.client = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
                region_name=os.getenv("AWS_REGION", "ap-northeast-2"), config=Config(signature_version="s3v4"))
        else:
            settings.local_storage_path.mkdir(parents=True, exist_ok=True)

    def new_key(self, suffix: str) -> str:
        return f"inspections/{uuid4().hex}{suffix.lower()}"

    def save(self, key: str, content: bytes, content_type: str) -> Path | None:
        if self.is_s3:
            self.client.put_object(Bucket=settings.s3_bucket, Key=key, Body=content, ContentType=content_type)
            return None
        path = settings.local_storage_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def read(self, key: str) -> bytes:
        if self.is_s3:
            return self.client.get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
        return (settings.local_storage_path / key).read_bytes()


storage = Storage()
