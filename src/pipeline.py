
"""Core ingestion, validation, and migration logic for DataMigrPipe."""

from __future__ import annotations

import csv
import json
import re
import sqlite3

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


@dataclass
class MigrationResult:
    """Summary of one migration run."""

    source_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    unique_loaded_rows: int
    destination_rows: int
    rejected_records: list[dict[str, Any]]



def load_csv(path: Path) -> list[dict[str, Any]]:
    """Read CSV records as dictionaries and detect the delimiter."""
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(file, dialect=dialect)

        if not reader.fieldnames:
            raise ValueError(f"{path} has no CSV header")

        # Remove whitespace and a possible BOM from column names.
        reader.fieldnames = [
            name.strip().lstrip("\ufeff") if name else name
            for name in reader.fieldnames
        ]

        return list(reader)



def load_json(path: Path) -> list[dict[str, Any]]:
    """Read a JSON array containing objects."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")

    if not all(isinstance(row, dict) for row in data):
        raise ValueError(f"{path} must contain JSON objects")

    return data


def normalize_and_validate(
    record: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Normalize a record or return validation errors."""

    # Make field names case-insensitive and ignore surrounding spaces.
    fields = {
        str(key).strip().lower(): value
        for key, value in record.items()
    }

    product_id = str(
        fields.get("product_id", fields.get("id", "")) or ""
    ).strip()

    product_name = str(
        fields.get("product_name", fields.get("name", "")) or ""
    ).strip()

    raw_price = fields.get("price")
    currency = str(fields.get("currency", "USD") or "").strip().upper()

    errors: list[str] = []

    if not product_id:
        errors.append("product_id is required")

    if not product_name:
        errors.append("product_name is required")

    try:
        price = Decimal(str(raw_price).strip())

        if not price.is_finite():
            errors.append("price must be a finite number")
        elif price < 0:
            errors.append("price must be non-negative")

    except (InvalidOperation, ValueError, AttributeError):
        price = None
        errors.append("price must be numeric")

    if not re.fullmatch(r"[A-Z]{3}", currency):
        errors.append("currency must be a three-letter code")

    if errors:
        return None, errors

    assert price is not None

    # Store money as a normalized decimal string.
    # This avoids floating-point arithmetic for currency values.
    normalized = {
        "product_id": product_id,
        "product_name": product_name,
        "price": format(price.quantize(Decimal("0.01")), "f"),
        "currency": currency,
    }

    return normalized, []


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the destination table if it does not exist."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            price TEXT NOT NULL,
            currency TEXT NOT NULL
                CHECK(length(currency) = 3),
            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.commit()


def upsert_products(
    connection: sqlite3.Connection,
    records: list[dict[str, Any]],
) -> int:
    """Insert new products or update existing product IDs."""

    connection.executemany(
        """
        INSERT INTO products (
            product_id,
            product_name,
            price,
            currency
        )
        VALUES (
            :product_id,
            :product_name,
            :price,
            :currency
        )
        ON CONFLICT(product_id) DO UPDATE SET
            product_name = excluded.product_name,
            price = excluded.price,
            currency = excluded.currency,
            updated_at = CURRENT_TIMESTAMP
        """,
        records,
    )

    connection.commit()
    return len(records)


def run_migration(
    data_dir: Path,
    database_path: Path,
    rejected_path: Path,
) -> MigrationResult:
    """Ingest, validate, migrate, and reconcile source records."""

    sources = [
        (
            "legacy_products.csv",
            load_csv(data_dir / "legacy_products.csv"),
        ),
        (
            "legacy_products.json",
            load_json(data_dir / "legacy_products.json"),
        ),
    ]

    accepted_by_id: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    source_rows = 0
    accepted_rows = 0
    duplicate_rows = 0

    for source_name, records in sources:
        for index, original in enumerate(records):
            source_rows += 1

            # CSV data rows begin on line 2 because line 1 is the header.
            row_number = index + (
                2 if source_name.endswith(".csv") else 1
            )

            normalized, errors = normalize_and_validate(original)

            if errors:
                rejected.append(
                    {
                        "source": source_name,
                        "row_number": row_number,
                        "record": original,
                        "errors": errors,
                    }
                )
                continue

            assert normalized is not None
            accepted_rows += 1

            product_id = normalized["product_id"]

            if product_id in accepted_by_id:
                duplicate_rows += 1

            # Last valid occurrence wins, including across source files.
            accepted_by_id[product_id] = normalized

    database_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.parent.mkdir(parents=True, exist_ok=True)

    accepted = list(accepted_by_id.values())

    with sqlite3.connect(database_path) as connection:
        create_schema(connection)
        upsert_products(connection, accepted)

        destination_rows = connection.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0]

    rejected_path.write_text(
        json.dumps(rejected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return MigrationResult(
        source_rows=source_rows,
        accepted_rows=accepted_rows,
        rejected_rows=len(rejected),
        duplicate_rows=duplicate_rows,
        unique_loaded_rows=len(accepted),
        destination_rows=destination_rows,
        rejected_records=rejected,
    )
