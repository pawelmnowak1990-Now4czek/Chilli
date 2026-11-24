# iOS Shortcuts

The step-by-step guide for both Shortcuts (Action Button screenshot and share-sheet link) is in
[docs/guides/ios-shortcuts.md](../docs/guides/ios-shortcuts.md).

In short: both send to `https://<your-domain>/capture` with the header
`Authorization: Bearer <CAPTURE_TOKEN>`; `<your-domain>` is the host from `PUBLIC_URL` in the server's `.env`.
