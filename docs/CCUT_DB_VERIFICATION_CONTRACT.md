# CCUT DB Verification Contract

Status: active as of 2026-07-29.

## Purpose

CCUT uses SQLite WAL. A proof that only hashes `ccut_app.db` is not a proof of
the live logical database state, because visible rows can live in `ccut_app.db-wal`.
The opposite is also true: two logically identical SQLite databases can have
different file bytes because page layout differs.

Therefore DB verification must distinguish:

- logical data hash: evidence of row-level content
- file SHA: only a byte-level artifact of one SQLite file
- WAL/SHM state: runtime metadata to record, not a data-invariance proof

Previous "DB unchanged" decisions that used only the `ccut_app.db` file hash do
not prove that WAL-applied data, including `structural_json`, was unchanged.

## Read-Only Verification Procedure

Verification must not mutate the live DB. Do not run `wal_checkpoint`,
`VACUUM`, `ANALYZE`, `REINDEX`, or any other write-capable maintenance command
as a verification precondition.

1. Open the live DB read-only enough to create a SQLite online backup.
2. Use the SQLite online backup API to create a consistent snapshot file.
3. Run all logical counts and hashes against the snapshot, not the live file.
4. Record live `ccut_app.db`, `ccut_app.db-wal`, and `ccut_app.db-shm` existence
   and sizes separately.

The snapshot file SHA may be recorded for artifact tracking, but it is not the
logical DB invariant.

## Logical Hash Contents

For each table:

- row count
- primary-key ordered row content hash
- JSON columns canonicalized before hashing

Also record:

- `sqlite_master` hash
- fragment order hash
- proposal set hash
- proposal content hash

JSON canonicalization means parsing JSON text when valid, then serializing with
sorted keys and compact separators before hashing. Invalid or non-JSON values
must be hashed as their original scalar representation.

## Backup Procedure

Operational backups for validation or rollback must use the SQLite online
backup API. Do not copy only `ccut_app.db` while WAL mode is active.

Restore procedure:

1. Stop the backend writer.
2. Preserve the current `ccut_app.db`, `ccut_app.db-wal`, and `ccut_app.db-shm`
   as evidence if present.
3. Restore the online-backup snapshot as `ccut_app.db`.
4. Remove stale `ccut_app.db-wal` and `ccut_app.db-shm` only after preserving
   them.
5. Start the backend.

Checkpointing is a maintenance operation. It may be useful in a separately
approved maintenance task, but it is not part of verification.
