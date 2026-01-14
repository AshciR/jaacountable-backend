#!/usr/bin/env python3
"""Test database connection to verify credentials and connectivity.

This script verifies that:
- DATABASE_URL is properly configured
- Database is accessible
- Connection pooling works correctly
- Basic queries can be executed

Usage:
    # For local development
    uv run python scripts/infrastructure/test-db-connection.py

    # For Supabase staging
    set -a; source .staging.env; set +a
    uv run python scripts/infrastructure/test-db-connection.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.database import DatabaseConfig


async def test_connection():
    """Test database connection and display connection information."""
    # Get DATABASE_URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable is not set")
        print("\nPlease set DATABASE_URL in your .env file or environment:")
        print("  export DATABASE_URL=postgresql+asyncpg://user:password@host:port/database")
        return False

    print("Testing database connection...")
    print(f"Database URL: {mask_password(database_url)}\n")

    # Create database config
    db_config = DatabaseConfig(database_url=database_url)

    try:
        # Create connection pool with small pool sizes for testing
        # Note: When connecting through Supabase pooler, use smaller pool sizes
        # to avoid exhausting Supabase's backend connection limits.
        # Supabase's Supavisor pooler already maintains hot connections and
        # intelligently shares them across clients.
        print("Creating connection pool (min_size=1, max_size=2 for testing)...")
        await db_config.create_pool(min_size=1, max_size=2)
        print("✅ Connection pool created successfully\n")

        # Get a connection and run test query
        print("Executing test query...")
        async with db_config.connection() as conn:
            # Query database information
            version = await conn.fetchval("SELECT version()")
            current_db = await conn.fetchval("SELECT current_database()")
            current_user_val = await conn.fetchval("SELECT current_user")

            print("✅ Query executed successfully\n")
            print("Database Information:")
            print(f"  PostgreSQL Version: {version}")
            print(f"  Current Database:   {current_db}")
            print(f"  Current User:       {current_user_val}")

        # Display pool statistics
        print("\nConnection Pool Statistics:")
        stats = db_config.get_pool_stats()
        print(f"  Pool Size:     {stats['size']}")
        print(f"  Idle:          {stats['idle']}")
        print(f"  Acquired:      {stats['acquired']}")
        print(f"  Min Size:      {stats['min_size']}")
        print(f"  Max Size:      {stats['max_size']}")

        # Detect if using Supabase and provide recommendations
        if "supabase.com" in database_url or "supabase.co" in database_url:
            print("\n💡 Supabase Connection Detected:")
            print("   When using Supabase pooler, consider smaller pool sizes in production")
            print("   to avoid exhausting backend connection limits. Supabase's Supavisor")
            print("   pooler already manages connection pooling efficiently.")
            print("\n   Recommended pool sizes for Supabase:")
            print("     - min_size: 2-5 (instead of default 10)")
            print("     - max_size: 10-15 (instead of default 20)")

        print("\n✅ Database connection test successful!")
        return True

    except Exception as e:
        print(f"\n❌ Database connection test failed!")
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Verify DATABASE_URL is correct")
        print("  2. Check network connectivity to database host")
        print("  3. Verify database credentials (username/password)")
        print("  4. Ensure database server is running and accepting connections")
        print("  5. Check firewall settings if using remote database")
        if "supabase" in database_url.lower():
            print("  6. Verify your Supabase project is not paused")
            print("  7. Check Supabase connection limits in your project dashboard")
        return False

    finally:
        # Clean up connection pool
        await db_config.close_pool()


def mask_password(url: str) -> str:
    """Mask password in database URL for safe display.

    Args:
        url: Database connection URL

    Returns:
        URL with password masked as '***'
    """
    if "://" not in url:
        return url

    # Split into protocol and rest
    protocol, rest = url.split("://", 1)

    # Check if there's a password
    if "@" not in rest:
        return url

    # Split into credentials and host
    credentials, host = rest.split("@", 1)

    # Check if there's a password in credentials
    if ":" not in credentials:
        return url

    # Mask the password
    username, _ = credentials.split(":", 1)
    masked_url = f"{protocol}://{username}:***@{host}"

    return masked_url


def main():
    """Main entry point."""
    try:
        # Run async test
        success = asyncio.run(test_connection())

        # Exit with appropriate status code
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
