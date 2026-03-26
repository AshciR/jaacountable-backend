"""Unit tests for DatabaseConfig.mask_url()."""

import pytest

from config.database import DatabaseConfig


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
