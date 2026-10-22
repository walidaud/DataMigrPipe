
import json
import sqlite3
from pathlib import Path

import pytest

from src.pipeline import (
    create_schema,
    normalize_and_validate,
    run_migration,
    upsert_products,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


def test_normalizes_valid_record():
    record = {
        " id ": " TOY-1 ",
        "name": "  Example Set ",
        "price": "12.5",
        "currency": "usd",
    }

    normalized, errors = normalize_and_validate(record)

    assert errors == []
    assert normalized == {
        "product_id": "TOY-1",
        "product_name": "Example Set",
        "price": "12.50",
        "currency": "USD",
    }


@pytest.mark.parametrize(
    "record, expected_error",
    [
        (
            {
                "product_id": "",
                "product_name": "Set",
                "price": "1",
                "currency": "USD",
            },
            "product_id is required",
        ),
        (
            {
                "product_id": "X",
                "product_name": "",
                "price": "1",
                "currency": "USD",
            },
            "product_name is required",
        ),
        (
            {
                "product_id": "X",
                "product_name": "Set",
                "price": "abc",
                "currency": "USD",
            },
            "price must be numeric",
        ),
        (
            {
                "product_id": "X",
                "product_name": "Set",
                "price": "-1",
                "currency": "USD",
            },
            "price must be non-negative",
        ),
        (
            {
                "product_id": "X",
                "product_name": "Set",
                "price": "1",
                "currency": "US",
            },
            "currency must be a three-letter code",
        ),
    ],
)
def test_rejects_invalid_records(record, expected_error):
    normalized, errors = normalize_and_validate(record)

    assert normalized is None
    assert expected_error in errors


def test_migration_counts_and_rejected_report(tmp_path):
    database = tmp_path / "migration.db"
    rejected_file = tmp_path / "rejected.json"

    result = run_migration(DATA_DIR, database, rejected_file)

    assert result.source_rows == 11
    assert result.accepted_rows == 8
    assert result.rejected_rows == 3
    assert result.duplicate_rows == 2
    assert result.unique_loaded_rows == 6
    assert result.destination_rows == 6

    rejected = json.loads(
        rejected_file.read_text(encoding="utf-8")
    )

    assert len(rejected) == 3
    assert all(item["errors"] for item in rejected)



def test_json_record_wins_for_duplicate_id(tmp_path):
    database = tmp_path / "migration.db"
    rejected_file = tmp_path / "rejected.json"

    run_migration(DATA_DIR, database, rejected_file)

    with sqlite3.connect(database) as connection:
        product = connection.execute(
            """
            SELECT product_name, price
            FROM products
            WHERE product_id = ?
            """,
            ("INV-101",),
        ).fetchone()

    assert product == ("USB-C Hub - Updated", "21.25")



def test_migration_is_idempotent(tmp_path):
    database = tmp_path / "migration.db"
    rejected_file = tmp_path / "rejected.json"

    run_migration(DATA_DIR, database, rejected_file)
    run_migration(DATA_DIR, database, rejected_file)

    with sqlite3.connect(database) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0]

    assert count == 6


def test_upsert_updates_existing_product(tmp_path):
    database = tmp_path / "products.db"

    original = {
        "product_id": "TOY-1",
        "product_name": "Original",
        "price": "1.00",
        "currency": "USD",
    }

    with sqlite3.connect(database) as connection:
        create_schema(connection)

        upsert_products(connection, [original])

        upsert_products(
            connection,
            [{**original, "product_name": "Updated"}],
        )

        product = connection.execute(
            "SELECT product_name FROM products WHERE product_id = ?",
            ("TOY-1",),
        ).fetchone()

    assert product == ("Updated",)
