
"""Command-line entry point for DataMigrPipe."""

from pathlib import Path

from src.pipeline import run_migration


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    result = run_migration(
        data_dir=project_root / "data",
        database_path=project_root / "output" / "migration.db",
        rejected_path=(
            project_root / "output" / "rejected_records.json"
        ),
    )

    print("\nDataMigrPipe - Migration complete")
    print("-" * 38)
    print(f"Source rows:       {result.source_rows}")
    print(f"Valid source rows: {result.accepted_rows}")
    print(f"Rejected rows:     {result.rejected_rows}")
    print(f"Duplicate IDs:     {result.duplicate_rows}")
    print(f"Unique loaded:     {result.unique_loaded_rows}")
    print(f"Destination rows:  {result.destination_rows}")
    print("\nDatabase: output/migration.db")
    print("Rejected report: output/rejected_records.json")


if __name__ == "__main__":
    main()
