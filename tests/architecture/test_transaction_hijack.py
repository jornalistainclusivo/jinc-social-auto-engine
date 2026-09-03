import ast
from pathlib import Path

import pytest


def test_no_commit_outside_uow():
    """
    15.5 Transaction Ownership Test / Hijack Test
    Ensures that repositories and adapters do not call commit() or rollback().
    """
    src_dir = Path("src/jinc_social_engine")

    for filepath in src_dir.rglob("*.py"):
        # We allow UoW and tests to have commit
        if "uow.py" in filepath.name or "test" in filepath.name:
            continue

        content = filepath.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("commit", "rollback"):
                        pytest.fail(
                            f"Found forbidden {node.func.attr}() call in {filepath}. "
                            f"Only UnitOfWork is allowed to manage transactions."
                        )
