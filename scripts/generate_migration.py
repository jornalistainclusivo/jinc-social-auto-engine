import os
import sys

from alembic.config import main as alembic_main
from testcontainers.postgres import PostgresContainer

if __name__ == "__main__":
    print("Starting PostgreSQL testcontainer...")
    with PostgresContainer("postgres:16-alpine") as postgres:
        # Get standard sync URL
        db_url = postgres.get_connection_url()
        # Convert to asyncpg URL for alembic
        async_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        os.environ["DATABASE_URL"] = async_url

        print(f"PostgreSQL started. DATABASE_URL={async_url}")
        print("Running Alembic revision --autogenerate...")

        sys.argv = ["alembic", "revision", "--autogenerate", "-m", "Initial migration"]
        alembic_main()
