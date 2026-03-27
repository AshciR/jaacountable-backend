"""Unit tests for DatabaseConfig.mask_url() and retry_with_backoff()."""

import asyncio
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from config.database import DatabaseConfig, retry_with_backoff


class TestMaskUrl:
    """DatabaseConfig.mask_url() masks credentials while preserving connection info."""

    async def test_masks_username_and_password(self):
        # Given: a URL with full credentials
        url = "postgresql://myuser:mypassword@localhost:5432/mydb"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: credentials are masked, host/port/db are preserved
        assert "myuser" not in result
        assert "mypassword" not in result
        assert "localhost" in result
        assert "5432" in result
        assert "mydb" in result

    async def test_shows_last_four_chars_of_username(self):
        # Given: a URL with a known username
        url = "postgresql://abcdefgh:secret@localhost/db"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: last 4 chars of username are visible, prefixed with ****
        assert "****efgh" in result

    async def test_shows_last_four_chars_of_password(self):
        # Given: a URL with a known password
        url = "postgresql://user:abcdefgh@localhost/db"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: last 4 chars of password are visible, prefixed with ****
        assert "****efgh" in result

    async def test_masks_supabase_style_url(self):
        # Given: a real-world style Supabase pooler URL
        url = "postgresql://postgres.rqoqwxyz:MyPass25!@aws-0-us-west-2.pooler.supabase.com:5432/postgres"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: credentials masked, host and db preserved
        assert "postgres.rqoqwxyz" not in result
        assert "MyPass25!" not in result
        assert "aws-0-us-west-2.pooler.supabase.com" in result
        assert "5432" in result
        assert result.endswith("/postgres")

    async def test_no_credentials_returns_url_unchanged(self):
        # Given: a URL with no credentials
        url = "postgresql://localhost:5432/mydb"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: URL is returned as-is (no userinfo to mask)
        assert result == url

    async def test_username_only_no_password(self):
        # Given: a URL with username but no password
        url = "postgresql://onlyuser@localhost/db"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: username is masked, no password segment added
        assert "onlyuser" not in result
        assert "****user" in result
        assert ":@" not in result

    async def test_short_username_still_masked(self):
        # Given: a username shorter than 4 chars
        url = "postgresql://ab:secret@localhost/db"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: entire short username is shown after ****
        assert "****ab" in result

    async def test_scheme_is_preserved(self):
        # Given: a postgresql:// URL
        url = "postgresql://user:pass@localhost/db"

        # When: mask_url is called
        result = DatabaseConfig.mask_url(url)

        # Then: scheme is unchanged
        assert result.startswith("postgresql://")

    async def test_asyncpg_style_url_scheme_preserved(self):
        # Given: a postgresql+asyncpg:// URL (before get_asyncpg_url conversion)
        url = "postgresql+asyncpg://user:pass@localhost/db"

        # When: mask_url is called directly on the raw URL
        result = DatabaseConfig.mask_url(url)

        # Then: scheme and host are preserved, raw credentials not present unmasked
        assert "postgresql+asyncpg://" in result
        assert "localhost" in result
        assert "****user" in result
        assert "****pass" in result
        assert "://user:" not in result


class TestRetryWithBackoff:
    """DatabaseConfig.create_pool() retries on transient failures with exponential backoff."""

    async def test_succeeds_on_first_attempt(self, test_database_url: str):
        # Given: a DatabaseConfig pointing at the real test database
        asyncpg_url = test_database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        db_config = DatabaseConfig(database_url=asyncpg_url)

        # When: create_pool is called
        try:
            pool = await db_config.create_pool(min_size=1, max_size=1)

            # Then: pool is created with the exact requested size
            assert pool is not None
            assert pool.get_size() == 1
        finally:
            await db_config.close_pool()

    async def test_retries_then_succeeds(self, test_database_url: str):
        # Given: a DatabaseConfig pointing at the real test database,
        #        where asyncpg.create_pool fails on the first attempt
        asyncpg_url = test_database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        db_config = DatabaseConfig(database_url=asyncpg_url)
        call_count = 0
        original_create_pool = asyncpg.create_pool

        async def flaky_create_pool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("simulated network blip on container wake-up")
            return await original_create_pool(*args, **kwargs)

        # When: create_pool is called (sleep patched to keep test fast)
        try:
            with patch("asyncpg.create_pool", side_effect=flaky_create_pool):
                with patch("config.database.asyncio.sleep", new_callable=AsyncMock):
                    pool = await db_config.create_pool(min_size=1, max_size=1, max_retries=3)

            # Then: pool is created after exactly 2 attempts
            assert pool is not None
            assert pool.get_size() == 1
            assert call_count == 2
        finally:
            await db_config.close_pool()

    async def test_raises_after_all_attempts_exhausted(self):
        # Given: a DatabaseConfig pointing at a port nothing is listening on
        db_config = DatabaseConfig(database_url="postgresql+asyncpg://user:password@localhost:1/db")

        # When / Then: all retries fail and the exception propagates
        with pytest.raises((OSError, asyncpg.PostgresConnectionError)):
            await db_config.create_pool(
                min_size=1,
                max_size=1,
                connect_timeout=1.0,
                max_retries=2,
                base_backoff=0.1,
            )

    async def test_does_not_retry_unregistered_exception(self, test_database_url: str):
        # Given: a DatabaseConfig where asyncpg.create_pool raises an unexpected error
        asyncpg_url = test_database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        db_config = DatabaseConfig(database_url=asyncpg_url)
        call_count = 0

        async def broken_create_pool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ValueError("unexpected programming error")

        # When / Then: ValueError propagates immediately without retry
        try:
            with patch("asyncpg.create_pool", side_effect=broken_create_pool):
                with pytest.raises(ValueError, match="unexpected programming error"):
                    await db_config.create_pool(min_size=1, max_size=1, max_retries=3)

            # And: only one attempt was made
            assert call_count == 1
        finally:
            await db_config.close_pool()

    async def test_max_retries_one_is_single_attempt(self, test_database_url: str):
        # Given: a DatabaseConfig where asyncpg.create_pool always fails
        asyncpg_url = test_database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        db_config = DatabaseConfig(database_url=asyncpg_url)
        call_count = 0

        async def always_fails(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise OSError("gone")

        # When: create_pool is called with max_retries=1
        try:
            with patch("asyncpg.create_pool", side_effect=always_fails):
                with pytest.raises(OSError):
                    await db_config.create_pool(min_size=1, max_size=1, max_retries=1)

            # Then: only one attempt, no further retries
            assert call_count == 1
        finally:
            await db_config.close_pool()
