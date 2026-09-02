import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
import procrastinate
from psycopg_pool import AsyncNullConnectionPool

# Database URL for SQLAlchemy using asyncpg
DB_URL_SA = "postgresql+asyncpg://jinc:jinc_gate1@localhost:15432/jinc_gate1"
# Database URL for Procrastinate using psycopg
DB_URL_PROC = "postgresql://jinc:jinc_gate1@localhost:15432/jinc_gate1"

engine = create_async_engine(DB_URL_SA, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Configure Procrastinate with NullPool to avoid initialization hangs on Windows
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=DB_URL_PROC,
        pool_factory=AsyncNullConnectionPool
    )
)

@app.task(name="test_task")
async def my_task(data: dict):
    pass

@pytest.fixture(autouse=True)
async def setup_db():
    # Setup schema
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS domain_state (id SERIAL PRIMARY KEY, status VARCHAR, data VARCHAR)"))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS audit_log (id SERIAL PRIMARY KEY, state_id INT, action VARCHAR)"))
    
    # Initialize Procrastinate schema using sync CLI or connector
    import subprocess
    subprocess.run(["procrastinate", "--app=test_gate1.app", "schema", "--apply"], env={"PGPASSWORD": "jinc_gate1", "PGUSER": "jinc", "PGHOST": "localhost", "PGPORT": "15432", "PGDATABASE": "jinc_gate1"}, check=True)
    
    yield
    
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS domain_state"))
        await conn.execute(text("DROP TABLE IF EXISTS audit_log"))
    await engine.dispose()

@pytest.mark.asyncio
async def test_g1_a_commit():
    """G1-A: Commit Atomicity"""
    async with app.open_async() as procrastinate_app:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # 1. CAS UPDATE / INSERT
                res = await session.execute(text("INSERT INTO domain_state (status, data) VALUES ('PENDING', 'test_a') RETURNING id"))
                state_id = res.scalar()
                await session.execute(text(f"INSERT INTO audit_log (state_id, action) VALUES ({state_id}, 'CREATE')"))
                
                # 3. Enqueue job
                await my_task.defer_async(data={"id": state_id})
                
        # Verify after commit
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT status FROM domain_state WHERE data='test_a'"))
            assert res.scalar() == 'PENDING'
            
            # Check if job exists
            async with procrastinate_app.connector.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM procrastinate_jobs WHERE task_name='test_task'")
                    jobs = await cur.fetchall()
                    assert len(jobs) > 0

@pytest.mark.asyncio
async def test_g1_b_rollback():
    """G1-B: Rollback Atomicity"""
    async with app.open_async() as procrastinate_app:
        # Clear jobs first
        async with procrastinate_app.connector.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM procrastinate_jobs")
                
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    # 1. CAS UPDATE / INSERT
                    res = await session.execute(text("INSERT INTO domain_state (status, data) VALUES ('PENDING', 'test_b') RETURNING id"))
                    state_id = res.scalar()
                    await session.execute(text(f"INSERT INTO audit_log (state_id, action) VALUES ({state_id}, 'CREATE')"))
                    
                    # 3. Enqueue job
                    await my_task.defer_async(data={"id": state_id})
                    
                    # Force rollback
                    raise ValueError("Force Rollback")
        except ValueError:
            pass
            
        # Verify after rollback
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT status FROM domain_state WHERE data='test_b'"))
            assert res.scalar() is None
            
            # Check if job exists
            async with procrastinate_app.connector.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM procrastinate_jobs WHERE task_name='test_task'")
                    jobs = await cur.fetchall()
                    # If the job exists, it means transactional dispatch FAILED!
                    assert len(jobs) == 0, "Job survived rollback! Transactional dispatch failed."
