<!-- BEGIN shared:db-migrations -->
## Schema and migrations

Two rules are easy to get wrong. The repository-specific section below
names the migration directories and files this project uses.

- **Before the first tagged release**, there is exactly one schema
  version. Do NOT add an incremental migration for a schema change: edit
  the initial schema in place. The pre-release history stays squashed into
  that clean v1 schema, so amend it rather than stacking migrations on
  top. Resetting development databases after the edit is the expected
  response to the runner's checksum mismatch, not a workaround.
- **Once a tagged release exists**, the released schema is frozen. Never
  edit an already-released migration file — the checksum check aborts
  anyway. Add a new numbered migration. Its baseline is the schema of the
  **immediately preceding released (tagged) version, NOT the previous
  commit or `HEAD~1`**. Production runs the last released schema, so the
  migration must upgrade cleanly from there. Unreleased migrations added
  since that tag belong to the in-progress release and may still be
  reworked, but the last *released* schema is never edited.
- Destructive changes are forward-only and follow expand/contract: add the
  new shape, migrate readers and writers, then remove the old shape in a
  later release. Never drop or rewrite a column in the same release that
  stops using it.
<!-- END shared:db-migrations -->
