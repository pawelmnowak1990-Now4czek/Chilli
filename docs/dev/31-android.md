# 31. Android guide

Chilli always worked with any phone (one HTTPS request), but the docs only described iPhone Shortcuts.

## What was built

- `docs/guides/android.md`: three share-sheet shortcuts in the free HTTP Shortcuts app
  (screenshot as a multipart `image` file, link and selected text as JSON). The JSON body is built by a
  one-line "Run before execution" script with `JSON.stringify`, because shared text from apps such as X
  contains quotes and line breaks that a hand-typed JSON template would break on.
- Links from README, `beginners.md`, `install-with-ai.md`, `browser-extension.md` and `shortcuts/README.md`.
- No server change: `/capture` already accepts both request shapes.

## Not verified yet

Written from the HTTP Shortcuts documentation (http-shortcuts.rmy.ch/advanced, /scripting), not on a
device. Menu labels may differ slightly by app version and phone maker; the request format matches
`app/capture.py` and was checked against it.
