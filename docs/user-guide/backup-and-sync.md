# Backups and sync

Both features encrypt on your device before anything leaves it. The storage
provider only ever sees encrypted blobs.

## Encrypted backups

```bash
sergio respaldo configurar /media/disco/sergio   # a folder
sergio respaldo configurar "s3://bucket/sergio?endpoint=https://s3.us-west-002.backblazeb2.com&region=us-west-002"
sergio respaldo configurar sftp://user@host:22/backups/sergio
sergio respaldo crear            # full the first time, then incremental
sergio respaldo crear --completo # force a full backup
sergio respaldo lista
sergio respaldo verificar        # decrypt and check every file, restore nothing
sergio respaldo restaurar                    # the latest, into a new folder
sergio respaldo restaurar --encima           # replaces ~/.openjarvis (keeps the old one aside)
```

- **What is saved:** everything in `~/.openjarvis` (memory, skills, notes,
  settings; API keys too unless `with_secrets = false`). SQLite databases are
  copied with SQLite's backup API, so a backup taken while Sergio runs is
  consistent.
- **Encryption:** each archive is a standard [age](https://age-encryption.org)
  file locked with your passphrase (scrypt + ChaCha20-Poly1305). `age -d`
  opens it without Sergio.
- **Passphrase:** asked every time, or read from `SERGIO_BACKUP_PASSPHRASE`.
  It is never stored. Lose it and the backups cannot be opened by anyone.
- **Integrity:** every archive's SHA-256 is recorded in an encrypted manifest
  that is written last, so an interrupted backup never looks complete.
- **Targets:** a folder; S3-compatible storage (AWS, Backblaze B2, Cloudflare
  R2, Wasabi, MinIO) with `SERGIO_S3_KEY_ID` / `SERGIO_S3_SECRET` in
  `sergio.env`; or any SSH server via `sftp`, using your SSH keys.

```toml
[backup]
target = ""        # set by `sergio respaldo configurar`
keep_full = 4      # complete chains kept on the target
with_secrets = true
```

## Sync between devices

```bash
sergio sync configurar s3://bucket/sergio-sync?endpoint=…   # same target on each device
sergio sync ahora
sergio sync estado
sergio sync olvidar      # this device forgets the key and stops syncing
```

Use the same target and the same passphrase (`SERGIO_SYNC_PASSPHRASE`) on each
device. What syncs: long-term memory, skills and notes (API keys only with
`with_secrets = true`).

- **Zero-knowledge:** a random data key is created once and stored on the
  target locked with your passphrase. Every object is encrypted with
  ChaCha20-Poly1305 and stored under an HMAC of its path, so even file names
  are hidden.
- **Conflicts:** when two devices changed the same file, the most recent edit
  wins and the other version is kept next to it as
  `name.conflicto-<device>`. Append-only logs are merged, and memory entries
  are merged one by one.
- **Deletions** only propagate when a device actually deleted a file; a
  missing or damaged manifest never deletes anything locally.

```toml
[sync]
target = ""
with_secrets = false
interval_minutes = 0   # 0 = only when you run `sergio sync ahora`
```
