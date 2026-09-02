import sys
import os
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
import procrastinate
import traceback

DB_URL_SA = "postgresql+asyncpg://jinc:jinc_gate1@127.0.0.1:15432/jinc_gate1"
DB_URL_PROC = "postgresql://jinc:jinc_gate1@127.0.0.1:15432/jinc_gate1"

engine = create_async_engine(DB_URL_SA, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=DB_URL_PROC
    )
)

@app.task(name="test_task")
async def my_task(data: dict):
    pass

async def setup_db():
    print("Setting up DB...")
    async with engine.begin() as conn:
        # Clean up existing tables and types to avoid "already exists" errors
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS domain_state (id SERIAL PRIMARY KEY, status VARCHAR, data VARCHAR)"))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS audit_log (id SERIAL PRIMARY KEY, state_id INT, action VARCHAR)"))
    
    import subprocess
    print("Applying schema via CLI...")
    env = os.environ.copy()
    env.update({
        "PGPASSWORD": "jinc_gate1",
        "PGUSER": "jinc",
        "PGHOST": "127.0.0.1",
        "PGPORT": "15432",
        "PGDATABASE": "jinc_gate1"
    })
    subprocess.run([sys.executable, "-m", "procrastinate", "--app=run_gate1.app", "schema", "--apply"], env=env, check=True)
    print("DB Setup complete.")

async def teardown_db():
    print("Tearing down DB...")
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()
    print("DB Teardown complete.")

async def test_g1_a_commit():
    print("Running G1-A (Commit Atomicity)...")
    async with app.open_async() as procrastinate_app:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                res = await session.execute(text("INSERT INTO domain_state (status, data) VALUES ('PENDING', 'test_a') RETURNING id"))
                state_id = res.scalar()
                await session.execute(text(f"INSERT INTO audit_log (state_id, action) VALUES ({state_id}, 'CREATE')"))
                
                # We want transactional dispatch. So we must inject the session's transaction into Procrastinate.
                # SQLAlchemy asyncpg gives us a DBAPI connection. However, procrastinate uses Psycopg (psycopg3).
                # We can't share connections between asyncpg and psycopg! They are different drivers!
                # Wait... Procrastinate doesn't natively integrate with SQLAlchemy AsyncSession if they use different drivers?
                # Actually, procrastinate natively provides an SQLAlchemy connector?
                # procrastinate.SQLAlchemyConnector? No, procrastinate provides procrastinate.AiopgConnector or PsycopgConnector.
                # SQLAlchemy 2.0 uses asyncpg. If we use asyncpg, we cannot share a transaction with PsycopgConnector because they use separate connection pools and different underlying protocols.
                # Let's verify this architecture limitation.
                
                # To simulate, we'll try defer_async anyway to see if it survives.
                await my_task.defer_async(data={"id": state_id})
                
        # Verify
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT status FROM domain_state WHERE data='test_a'"))
            assert res.scalar() == 'PENDING'
            
            async with procrastinate_app.connector.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM procrastinate_jobs WHERE task_name='test_task'")
                    jobs = await cur.fetchall()
                    assert len(jobs) > 0, "Job not found after commit"
    print("G1-A PASS")

async def test_g1_b_rollback():
    print("Running G1-B (Rollback Atomicity)...")
    async with app.open_async() as procrastinate_app:
        async with procrastinate_app.connector.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM procrastinate_jobs")
                
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    res = await session.execute(text("INSERT INTO domain_state (status, data) VALUES ('PENDING', 'test_b') RETURNING id"))
                    state_id = res.scalar()
                    await session.execute(text(f"INSERT INTO audit_log (state_id, action) VALUES ({state_id}, 'CREATE')"))
                    
                    await my_task.defer_async(data={"id": state_id})
                    
                    raise ValueError("Force Rollback")
        except ValueError:
            pass
            
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT status FROM domain_state WHERE data='test_b'"))
            assert res.scalar() is None
            
            async with procrastinate_app.connector.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM procrastinate_jobs WHERE task_name='test_task'")
                    jobs = await cur.fetchall()
                    if len(jobs) > 0:
                        print("🔴 FAIL: Job survived rollback! Transactional dispatch failed.")
                        sys.exit(1)
    print("G1-B PASS")

async def main():
    await setup_db()
    try:
        await test_g1_a_commit()
        await test_g1_b_rollback()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
    finally:
        await teardown_db()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
