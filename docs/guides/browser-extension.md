# Browser extension

A small extension (Manifest V3, plain JavaScript, no build step) for Chrome and other Chromium
browsers: Edge, Brave, Arc, Dia, Vivaldi. It sends the same captures as the phone shortcuts (iPhone or Android) and shows
what you already saved about the page you are on.

## Install

1. Download `chilli-extension-<version>.zip` from the latest
   [release](https://github.com/pawelmnowak1990-Now4czek/chilli/releases/latest) and unzip it.
   Keep the unzipped folder where it is: the browser loads the extension from it.
   (Or use the `extension` folder of a git checkout.)
2. Open the extensions page: `chrome://extensions` (Edge: `edge://extensions`, Brave: `brave://extensions`,
   Dia: `dia://extensions`).
3. Turn on **Developer mode**.
4. **Load unpacked** → choose the unzipped folder (the one that contains `manifest.json`).
5. Pin the chilli icon to the toolbar (the puzzle icon → the pin next to Chilli).

The options page opens on first install (later: right-click the icon → Options).

## Options

- **Server address**: your `PUBLIC_URL`, e.g. `https://chilli.example.com`.
- **Token**: the `CAPTURE_TOKEN` (the same as in the phone shortcuts). It stays in this browser only
  (`chrome.storage.local`, not synced).
- **Show what I already have**: on by default; see below.

Click **Save**. The browser asks for permission to access that one server; allow it. The extension
asks for no other site access in advance (only `optional_host_permissions`). Then **Test connection**
should say that the connection and the token work.

Some browsers (Dia, Arc) also have a per-site access switch on the extension's details page; if
saves fail with a connection error, check that the Chilli server is allowed there.

## Use

- **Toolbar icon**: saves the selected text, or the page address when nothing is selected.
- **Right-click menu**: Save page, Save link (on a link), Save selection, Save tab screenshot,
  Related saves in Chilli.
- **Alt+Shift+S**: screenshot of the visible part of the tab (sent with the page address, so Chilli
  also fetches the full article).
- **Alt+Shift+R**: the list of related saves for this page. Change the keys at `chrome://extensions/shortcuts`.

The icon shows the result: a green ✓ (disappears after 3 seconds) or a red ! with the error in the
tooltip. Without a server address, token or permission, a save opens the options page instead.

## "You already have something on this"

When a page opens, the extension sends its address and title to your server (`POST /related`,
in the request body, so it does not land in logs) and shows on the icon:

- a number (orange): how many related saves you have,
- a blue dot: this page is already saved.

The tooltip lists the titles; Alt+Shift+R opens the list with links. Incognito tabs and your own
server are skipped. Turn it off in the options if you do not want page addresses sent to the server.
The answer contains only titles, addresses, dates and kinds, because the extension holds the capture
token only.

## Update

Download and unzip the new release over the old folder (or `git pull` in the checkout), then click
the reload arrow next to Chilli on the extensions page. If an update
changes permissions, open the options and click **Save** once to grant access again.

## Limits

- Browser pages such as `chrome://...`, the extension store and the built-in PDF viewer do not allow
  extensions to read the page: screenshots and selections may fail there.
- Selections up to 200,000 characters are stored; the model reads the first 30,000.
- Not in the Chrome Web Store yet: install from the folder as above. Safari is not supported yet.
- Privacy: what the extension sends and stores is in [docs/extension-privacy.md](../extension-privacy.md).
