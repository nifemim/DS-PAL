---
title: "Secure zip extraction prevents path traversal and zip bombs"
category: security-issues
tags:
  - zipfile
  - path-traversal
  - streaming
  - zip-bomb
  - data-loading
module: app.services.dataset_loader
symptom: |
  ZIP archives from untrusted HTTP sources (data.gov, generic URLs) could write
  files outside the intended cache directory via crafted entries like `../../evil.csv`.
  No protection against zip bombs (small compressed files decompressing to gigabytes).
root_cause: |
  `zipfile.ZipFile.extract()` preserves directory structure from the archive without
  validating that resolved paths stay within the target directory. Python's zipfile
  module strips `..` since ~2014, but the docs still warn against trusting this for
  untrusted archives. Additionally, `ZipInfo.file_size` is attacker-controlled metadata
  and cannot be trusted for size enforcement.
date_solved: 2026-03-06
tickets: "#70"
---

# Secure Zip Extraction Prevents Path Traversal and Zip Bombs

## Problem

The `_extract_zip()` function in `dataset_loader.py` used `zf.extract(f, cache_dir)` directly on untrusted archive contents downloaded from remote sources. This is a textbook **zip slip** vulnerability — a malicious zip entry named `../../etc/cron.d/backdoor.csv` would pass the extension filter and write outside the cache directory.

Additionally, there was no zip bomb protection. A small compressed file could decompress to gigabytes, and `ZipInfo.file_size` (the only pre-flight size indicator) is metadata the attacker controls.

## What Didn't Work

- **Relying on `ZipInfo.file_size` alone for size limits** — this is declared in the zip header and can be spoofed. A zip bomb can report `file_size = 1024` while actually decompressing to gigabytes.
- **Using `zf.read(f)` into memory** — avoids symlink attacks but loads the entire decompressed entry into RAM before you can check its size. A 50MB compressed CSV could decompress to 500MB+ in memory.
- **Compression ratio heuristics** — uses `file_size / compress_size` which is also attacker-controlled. Redundant if you have runtime byte counting.

## Solution

Three-layer defense, all in `_extract_zip()`:

### 1. Flatten filenames with `Path.name`

```python
safe_name = Path(info.filename).name
if not safe_name or safe_name.startswith("."):
    continue
```

`Path("../../evil.csv").name` returns `"evil.csv"`. This strips all directory components including `../`. Skip empty names (directory entries) and dot-files.

### 2. Stream to disk with runtime byte counting

```python
member_bytes = 0
with zf.open(info) as src, open(dest, "wb") as out:
    while True:
        chunk = src.read(65536)
        if not chunk:
            break
        member_bytes += len(chunk)
        total_bytes += len(chunk)
        if member_bytes > MAX_FILE_BYTES:
            raise ValueError(...)
        if total_bytes > MAX_TOTAL_EXTRACT:
            raise ValueError(...)
        out.write(chunk)
```

`zf.open()` returns a streaming file-like object. Write chunks directly to disk — never hold the full decompressed content in memory. Count actual bytes decompressed (not the metadata). Enforce both per-file and total limits.

### 3. Belt-and-suspenders containment check

```python
dest = (cache_dir / safe_name).resolve()
if not dest.is_relative_to(cache_dir.resolve()):
    raise ValueError(...)
```

Use `Path.is_relative_to()` (Python 3.9+) instead of `str.startswith()` — the string approach has a subtle bug where `/tmp/foo` passes for `/tmp/foobar/...`.

### 4. Cleanup on error

```python
except ValueError:
    dest.unlink(missing_ok=True)
    for f in extracted:
        f.unlink(missing_ok=True)
    raise
```

If extraction fails midway (size limit hit on second file), clean up both the partial file and any previously extracted files.

## Key Gotchas

- **`ZipInfo.file_size` is untrusted** — never use it as the sole size guard. Use runtime byte counting during decompression.
- **`zf.read()` defeats streaming** — loads everything into memory. Use `zf.open()` + chunked reads instead.
- **`str.startswith()` for path containment is buggy** — `/tmp/foo` matches `/tmp/foobar`. Use `Path.is_relative_to()`.
- **`zipfile.extract()` in Python does strip `..`** since ~2014, but the official docs still say "never extract archives from untrusted sources without prior inspection."
- **Kaggle uses its own extraction** — `api.dataset_download_files(unzip=True)` bypasses `_extract_zip` entirely. Separate code path, separate risk assessment.

## Prevention

- Always use the read-and-write pattern for untrusted archives, never `zf.extract()`
- Define `SUPPORTED_DATA_EXTENSIONS` as a module constant and reuse it across cache lookup, zip extraction, and file loading
- When adding new file format support, update all pipeline stages (per the Zenodo learning)

## Related

- `docs/solutions/integration-issues/zenodo-dataset-download-requires-rest-api.md` — zip extraction context, extension consistency
- `docs/solutions/integration-issues/provider-download-returns-html-not-data.md` — content validation before parsing
- Python zipfile docs: https://docs.python.org/3/library/zipfile.html
- Snyk Zip Slip research: https://github.com/snyk/zip-slip-vulnerability
