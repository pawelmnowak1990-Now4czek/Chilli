# 29. Browser extension as a release download

Installing the extension used to need a git checkout. Now every published GitHub release carries
`chilli-extension-<version>.zip`, so people download, unzip and load it.

## What was built

- `.github/workflows/release-extension.yml`: on `release: published`, packs `extension/` (version from
  `manifest.json`, hidden files left out) and attaches the zip with `gh release upload --clobber`.
  It runs on the published release, not on the tag push, because a file can only be attached to a
  release that exists; `--clobber` lets a re-run replace the file.
- `docs/guides/browser-extension.md`: install and update from the zip; git checkout still works.
- README Quick start step 4 and an optional section in `docs/guides/beginners.md`.

## How to check

Publish a release (or re-run the workflow on one): the release page lists the zip. Unzip it and load
it with **Load unpacked**; `manifest.json` must sit directly in the chosen folder.

Next: a Chrome Web Store listing (privacy policy, screenshots, permission justifications) and, later,
a Safari build with `xcrun safari-web-extension-converter`.

## Chrome Web Store package

- `docs/extension-privacy.md`: the privacy policy the store requires (what is sent where, what is
  stored, permissions), linked from the extension guide.
- `docs/dev/chrome-web-store.md`: maintainer steps, listing texts, permission justifications and the
  data-usage answers, ready to paste.
- `docs/assets/store/`: three 1280×800 screenshots and the 440×280 promo tile, rendered from
  `store.html` with `node render.js` (Playwright). They are illustrations of the real UI (same texts
  as `options.html`, `related.html` and the menu items in `background.js`), not screen captures.
