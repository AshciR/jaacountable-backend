"""Shared utilities for production scripts (discovery and classification)."""

from pathlib import Path

from botocore.client import BaseClient

from src.storage.s3 import upload_file


def upload_jsonl_to_s3(
    client: BaseClient,
    local_path: Path,
    bucket: str,
    news_source: str,
    date_str: str,
) -> None:
    """Upload a JSONL discovery file to S3.

    The object key follows the convention: {news_source}/{date_str}.jsonl

    Args:
        client: Boto3 S3 client.
        local_path: Path to the local JSONL file to upload.
        bucket: Target S3 bucket name.
        news_source: News source identifier used as the top-level folder (e.g. "gleaner").
        date_str: Date string used as the filename stem (e.g. "2026-04-01").

    Raises:
        botocore.exceptions.BotoCoreError: On upload failure.
    """
    key = f"{news_source}/{date_str}.jsonl"
    upload_file(client, local_path, bucket, key, content_type="application/x-ndjson")


def upload_log_to_s3(
    client: BaseClient,
    local_path: Path,
    bucket: str,
    news_source: str,
    timestamp: str,
    log_type: str,
) -> None:
    """Upload a log file to S3.

    The object key follows the convention:
        {news_source}/logs/{news_source}_{log_type}_{timestamp}.log

    Args:
        client: Boto3 S3 client.
        local_path: Path to the local log file to upload.
        bucket: Target S3 bucket name.
        news_source: News source identifier (e.g. "gleaner", "observer").
        timestamp: Timestamp string (e.g. "2026-04-01_12-30-00").
        log_type: Stage identifier (e.g. "discovery", "classification").

    Raises:
        botocore.exceptions.BotoCoreError: On upload failure.
    """
    key = f"{news_source}/logs/{news_source}_{log_type}_{timestamp}.log"
    upload_file(client, local_path, bucket, key, content_type="text/plain")


def upload_classification_result_to_s3(
    client: BaseClient,
    local_path: Path,
    bucket: str,
    news_source: str,
    timestamp: str,
) -> None:
    """Upload a classification result JSON file to S3.

    The object key follows the convention:
        {news_source}/classification_results/{news_source}_classification_{timestamp}.json

    Args:
        client: Boto3 S3 client.
        local_path: Path to the local JSON result file to upload.
        bucket: Target S3 bucket name.
        news_source: News source identifier (e.g. "gleaner", "observer").
        timestamp: Timestamp string (e.g. "2026-04-01_12-30-00").

    Raises:
        botocore.exceptions.BotoCoreError: On upload failure.
    """
    key = f"{news_source}/classification_results/{news_source}_classification_{timestamp}.json"
    upload_file(client, local_path, bucket, key, content_type="application/json")


def upload_classification_errors_to_s3(
    client: BaseClient,
    local_path: Path,
    bucket: str,
    news_source: str,
    timestamp: str,
) -> None:
    """Upload a classification error JSONL file to S3.

    The object key follows the convention:
        {news_source}/classification_results/{news_source}_classification_{timestamp}_errors.jsonl

    Args:
        client: Boto3 S3 client.
        local_path: Path to the local JSONL error file to upload.
        bucket: Target S3 bucket name.
        news_source: News source identifier (e.g. "gleaner", "observer").
        timestamp: Timestamp string (e.g. "2026-04-01_12-30-00").

    Raises:
        botocore.exceptions.BotoCoreError: On upload failure.
    """
    key = f"{news_source}/classification_results/{news_source}_classification_{timestamp}_errors.jsonl"
    upload_file(client, local_path, bucket, key, content_type="application/x-ndjson")
