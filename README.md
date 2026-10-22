
# DataMigrPipe

A Python-based data migration pipeline that ingests legacy CSV
and JSON records, validates and transforms them, and migrates
clean records into a SQLite database.

## Features

- CSV and JSON ingestion
- Field normalization and data validation
- Duplicate detection and deterministic conflict resolution
- Invalid-record reporting with source and row information
- SQLite upserts with primary-key constraints
- Migration reconciliation and record counts
- Automated tests with pytest
- GitHub Actions CI workflow

## Technology Stack

- Python 3.12
- SQL and SQLite
- CSV and JSON
- pytest
- Git and GitHub
- GitHub Actions

## Getting Started

### Requirements

- Python 3.12
- Git
- Visual Studio Code (recommended)

### Setup

Create and activate a virtual environment, then install
the test dependency.

Windows PowerShell:

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt

macOS/Linux:

    python3.12 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt

### Run the migration

    python -m src.migrate

The pipeline creates:

- output/migration.db
- output/rejected_records.json

### Run automated tests

    python -m pytest -v

## Data Quality Rules

- Product IDs are required and trimmed.
- Product names are required and trimmed.
- Prices must be numeric, finite, and non-negative.
- Currency codes must contain three letters and are normalized
  to uppercase.
- Common source-field aliases are supported.
- Invalid records are reported instead of loaded.
- The last valid occurrence of a duplicate product ID wins.
- Database upserts prevent duplicate primary-key rows on reruns.

## Testing Strategy

Tests cover field normalization, invalid records, migration
counts, duplicate resolution, upsert behavior, and idempotency.

GitHub Actions runs the test suite on pushes and pull requests
and executes the sample migration.
