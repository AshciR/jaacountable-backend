"""Tests for S3 storage helpers using a LocalStack container."""

from collections.abc import Callable
from pathlib import Path

from src.storage.s3 import upload_file

BUCKET = "test-article-discovery"


class TestUploadFile:
    def test_file_contents_are_preserved(self, s3_client: Callable, tmp_path: Path):
        # Given a local file with known content
        local_file = tmp_path / "articles.jsonl"
        content = '{"url": "https://jamaica-gleaner.com/article/1"}\n'
        local_file.write_text(content)
        client = s3_client(BUCKET)

        # When the file is uploaded
        upload_file(client, local_file, BUCKET, "test/articles.jsonl", "application/x-ndjson")

        # Then the object body matches the original file
        response = client.get_object(Bucket=BUCKET, Key="test/articles.jsonl")
        assert response["Body"].read().decode() == content

    def test_content_type_is_set(self, s3_client: Callable, tmp_path: Path):
        # Given a local log file
        local_file = tmp_path / "run.log"
        local_file.write_text("INFO discovery started\n")
        client = s3_client(BUCKET)

        # When uploaded with text/plain content type
        upload_file(client, local_file, BUCKET, "test/run.log", "text/plain")

        # Then the stored object has the correct content type
        response = client.head_object(Bucket=BUCKET, Key="test/run.log")
        assert response["ContentType"] == "text/plain"
