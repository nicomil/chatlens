# What is in here that is not ours

One file, and this note exists so that a reader can tell which.

| File | Version | SHA-256 | From |
|---|---|---|---|
| `htmx.min.js` | 2.0.4 | `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447` | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js |

`style.css`, `app.js` and `theme.js` are ours.

## Why it is vendored rather than fetched

The dashboard works offline, on a laptop, on conference wifi, and in a room with
no network at all. A `<script src>` pointing at a CDN would make every page
depend on a third party being reachable — and the content security policy this
server sends is `script-src 'self'`, which forbids it anyway.

## Why the version and the hash are written down

They were not, and that is the whole point of this file. The filename carries no
version, so the only way to know which htmx was in a release was to read the
minified source, and nothing would have noticed a file swapped by accident
during a merge or an editor's "save all". `tests/test_dashboard.py` checks the
hash, so a change to this file is a change somebody has to make on purpose.

## Updating it

Replace the file, then put the new version and the new hash in the table above
and in the test. Do the two together: the test failing is the reminder, and a
hash updated without reading the release notes is worse than no hash at all.

```bash
curl -sL https://unpkg.com/htmx.org@<version>/dist/htmx.min.js \
  -o src/chatlens/web/static/htmx.min.js
shasum -a 256 src/chatlens/web/static/htmx.min.js
```
