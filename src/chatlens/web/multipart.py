"""Reading an uploaded file, since the standard library no longer will.

`cgi.FieldStorage` did this, was deprecated in 3.11 and removed in 3.13, and we
support 3.11 to 3.13. So it is written here, and written to two rules that the
removed one did not follow.

**It streams.** The rest of the server reads a request body with
`rfile.read(length)`, which is fine for a form and wrong for a file: a dataset
is tens of megabytes and a limit refused after reading is not a limit. Here the
body is read in blocks, written straight to disk, and the limit is applied as it
goes.

**It refuses rather than repairs.** A part with no name, a boundary that never
arrives, a body that stops in the middle: each is an error with a sentence
saying what was wrong. Guessing at a malformed upload is how you end up with
half a dataset that looks whole.

What it does not do is the whole of RFC 7578 — no nested multipart, no
`Content-Transfer-Encoding`, no header continuation lines. Browsers posting a
form do not send those, and covering them would be code nobody here can check.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

BLOCK = 64 * 1024

# `boundary=...`, quoted or not, per RFC 2045.
BOUNDARY_RE = re.compile(r'boundary=(?:"([^"]+)"|([^\s;]+))', re.IGNORECASE)

# `name="x"; filename="y"`, the only two we look at.
PARAM_RE = re.compile(r'(\w+)="([^"]*)"')


class UploadError(RuntimeError):
    """Something about the upload is wrong, phrased for the person who sent
    it."""


class TooLarge(UploadError):
    """The upload went past the limit, and was stopped while it was going."""


class _Reader:
    """The request body, with a limit and somewhere to put bytes back.

    Pushback is what lets the parser recognise a boundary that straddles two
    blocks without holding the whole body in memory.
    """

    def __init__(self, stream, length: int):
        self.stream = stream
        self.remaining = length
        self.pending = b''

    def read(self, size: int = BLOCK) -> bytes:
        if self.pending:
            chunk, self.pending = self.pending[:size], self.pending[size:]
            return chunk
        if self.remaining <= 0:
            return b''
        chunk = self.stream.read(min(size, self.remaining))
        self.remaining -= len(chunk)
        return chunk

    def push_back(self, data: bytes) -> None:
        self.pending = data + self.pending

    def read_line(self, limit: int = 8192) -> bytes:
        """One CRLF-terminated line, for the headers.

        The limit is on the line, not on how much happened to be read looking
        for it: a block is far longer than a header, and measuring the buffer
        rejected perfectly ordinary uploads.
        """
        out = b''
        while b'\n' not in out:
            chunk = self.read(BLOCK)
            if not chunk:
                break
            out += chunk
            if b'\n' not in out and len(out) > limit:
                raise UploadError('A header line in the upload is too long.')
        line, separator, rest = out.partition(b'\n')
        if rest or separator:
            self.push_back(rest)
        return line + separator


def boundary_of(content_type: str) -> bytes:
    """The delimiter this upload is divided by."""
    if 'multipart/form-data' not in (content_type or '').lower():
        raise UploadError('That was not a file upload.')
    match = BOUNDARY_RE.search(content_type or '')
    if not match:
        raise UploadError('The upload has no boundary marker: it is malformed.')
    return (match.group(1) or match.group(2)).encode('ascii', 'replace')


def _headers(reader: _Reader) -> dict:
    """A part's headers, up to the blank line."""
    headers = {}
    while True:
        line = reader.read_line()
        if not line:
            raise UploadError('The upload ended inside a part\'s headers.')
        stripped = line.strip()
        if not stripped:
            return headers
        name, separator, value = stripped.decode('utf-8', 'replace').partition(':')
        if not separator:
            raise UploadError('A malformed header line in the upload.')
        headers[name.strip().lower()] = value.strip()


def _copy_until(reader: _Reader, delimiter: bytes, sink, limit: int) -> int:
    """Copy a part's body to `sink`, stopping at `delimiter`.

    The last `len(delimiter) - 1` bytes are held back on every pass, because a
    delimiter split across two blocks would otherwise be missed and its two
    halves written into the file.
    """
    buffer = b''
    written = 0
    keep = len(delimiter) - 1
    while True:
        chunk = reader.read()
        if not chunk:
            raise UploadError('The upload ended in the middle of a file. '
                              'Nothing was kept.')
        buffer += chunk
        index = buffer.find(delimiter)
        if index >= 0:
            written += index
            if written > limit:
                # Checked here as well as below: a file smaller than one block
                # arrives whole, and would otherwise sail past the limit
                # because the loop never took the other branch.
                raise TooLarge(
                    f'The file is larger than the {limit // (1024 * 1024)} MB '
                    f'limit. Nothing was kept.')
            sink(buffer[:index])
            reader.push_back(buffer[index + len(delimiter):])
            return written

        if len(buffer) > keep:
            out, buffer = buffer[:len(buffer) - keep], buffer[len(buffer) - keep:]
            sink(out)
            written += len(out)
            if written > limit:
                raise TooLarge(
                    f'The file is larger than the {limit // (1024 * 1024)} MB '
                    f'limit. Nothing was kept.')


def parse(stream, content_length: int, content_type: str, *,
          save_dir: Path, max_bytes: int,
          allowed_suffixes=('.csv',)) -> tuple[dict, list]:
    """Read the upload. Returns the plain fields and the files saved.

    Files land in `save_dir` under temporary names; naming them properly is the
    caller's business, because only the caller knows whether it is replacing
    something. A part that fails leaves no file behind.
    """
    boundary = boundary_of(content_type)
    if content_length > max_bytes + 1024 * 1024:
        # Declared too large before a byte is read: refuse it here rather than
        # discovering it a hundred megabytes in.
        raise TooLarge(
            f'The upload declares {content_length // (1024 * 1024)} MB, over '
            f'the {max_bytes // (1024 * 1024)} MB limit.')

    reader = _Reader(stream, content_length)
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    opening = b'--' + boundary
    separator = b'\r\n--' + boundary

    first = reader.read_line()
    if first.strip() != opening:
        raise UploadError('The upload does not start with its boundary: it is '
                          'malformed.')

    fields, files = {}, []
    try:
        while True:
            headers = _headers(reader)
            disposition = headers.get('content-disposition', '')
            params = dict(PARAM_RE.findall(disposition))
            name = params.get('name')
            if not name:
                raise UploadError('A part of the upload has no name.')

            filename = params.get('filename')
            if filename is None:
                # A plain form field: small by nature, kept in memory.
                collected = bytearray()
                _copy_until(reader, separator, collected.extend, 1024 * 1024)
                fields[name] = bytes(collected).decode('utf-8', 'replace')
            elif not filename:
                # An empty file input: the browser sends the part anyway.
                _copy_until(reader, separator, lambda _b: None, max_bytes)
            else:
                safe = Path(filename).name          # never a path
                if not safe or Path(safe).suffix.lower() not in allowed_suffixes:
                    raise UploadError(
                        f'"{filename}" is not one of the accepted kinds '
                        f'({", ".join(allowed_suffixes)}).')
                handle = tempfile.NamedTemporaryFile(
                    dir=save_dir, prefix='.upload-', suffix='.part',
                    delete=False)
                temporary = Path(handle.name)
                try:
                    size = _copy_until(reader, separator, handle.write,
                                       max_bytes)
                    handle.close()
                except BaseException:
                    handle.close()
                    temporary.unlink(missing_ok=True)
                    raise
                files.append(dict(field=name, filename=safe, path=temporary,
                                  size=size))

            tail = reader.read(2)
            if tail == b'--':
                return fields, files
            if tail != b'\r\n':
                raise UploadError('The upload is malformed after a part.')
    except BaseException:
        # Half an upload leaves nothing behind: a partial file with a plausible
        # name is worse than no file.
        for saved in files:
            Path(saved['path']).unlink(missing_ok=True)
        raise
