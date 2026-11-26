# Chrome Web Store listing

Everything needed to publish the extension in the Chrome Web Store (and the same package in
Microsoft Edge Add-ons). The maintainer does the steps that need an account; the texts and images
below are ready to paste.

## Steps for the maintainer

1. Register at the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
   (one-time registration fee, Google account, identity verification).
2. The repository must be public, because the privacy policy link points at it.
3. Get the zip: from the latest GitHub release (`chilli-extension-<version>.zip`), or
   `cd extension && zip -r ../chilli-extension.zip . -x '.*'`.
4. **New item** → upload the zip, then fill the tabs as below and **Submit for review**.
5. After approval: add the store link to `docs/guides/browser-extension.md`, the README and
   `docs/guides/beginners.md`.
6. Each new version: raise `version` in `extension/manifest.json`, publish the release, upload its zip
   in the dashboard (**Package** → **Upload new package**).

Edge: [Partner Center](https://partner.microsoft.com/dashboard/microsoftedge/) (free), same zip and texts.

## Store listing

- **Name:** Chilli
- **Summary** (max 132 characters): Save a page, selection or tab screenshot to your own Chilli knowledge base in one click, and see what you already saved about it.
  (Same as `description` in `manifest.json`, which the store uses.)
- **Category:** Productivity → Tools (or Workflow & Planning)
- **Language:** English
- **Description:**

```
Chilli is a free, open-source knowledge base you host yourself. This extension sends what you are
looking at to your own Chilli server in one click; your AI model describes it there, and your AI
assistant (Claude, Cursor and other MCP clients) can search it later.

• One click: the toolbar icon saves the selected text, or the page when nothing is selected.
• Right-click: save the page, a link, the selection or a screenshot of the tab (Alt+Shift+S).
• "You already have something on this": the icon shows how many related saves you have for the
  page you are on; Alt+Shift+R lists them with links.
• No folders, tags or titles: the model on your server classifies every save.

Requires your own Chilli server (Docker, a small VPS or a home machine). Setup guide:
https://github.com/pawelmnowak1990-Now4czek/chilli

Privacy: the extension talks only to the server address you enter. No analytics, no tracking,
nothing is sent to the authors.
```

- **Images** (in `docs/assets/store/`, source `store.html`, render with `node render.js`):
  - store icon 128×128: `extension/icons/chilli-128.png`
  - screenshots 1280×800: `screenshot-save-1280x800.png`, `screenshot-related-1280x800.png`,
    `screenshot-options-1280x800.png`
  - small promo tile 440×280: `promo-tile-440x280.png`
- **Homepage URL:** https://github.com/pawelmnowak1990-Now4czek/chilli
- **Support URL:** https://github.com/pawelmnowak1990-Now4czek/chilli/issues

## Privacy practices tab

- **Single purpose:** Save the current page, link, selected text or tab screenshot to the user's own
  self-hosted Chilli server, and show which related saves already exist there.
- **Permission justifications:**
  - `contextMenus`: adds the "Save page/link/selection/tab screenshot to Chilli" and "Related saves
    in Chilli" items to the right-click menu.
  - `activeTab`: takes a screenshot of the visible part of the tab when the user chooses "Save tab
    screenshot" or presses the shortcut.
  - `scripting`: reads the text the user selected on the page when they save a selection.
  - `tabs`: reads the address and title of the active tab, to save it and to show the count of
    related saves on the icon when a page opens.
  - `storage`: keeps the user's server address, capture token and one setting, locally.
  - Host permissions (optional, `https://*/*`, `http://localhost/*`, `http://127.0.0.1/*`): every user
    runs their own server at their own address, so the address cannot be listed in advance. The
    extension requests access only to the one address the user enters in the options, at that moment.
- **Remote code:** No, I am not using remote code.
- **Data usage:** collected: **Web history** (page addresses and titles) and **Website content**
  (selected text, screenshots), only when the user saves or (with the setting on) to look up related
  saves; **Authentication information** (the user's own capture token, stored locally). All of it goes
  only to the user's own server. Certify: not sold to third parties; not used or transferred for
  purposes unrelated to the single purpose; not used for creditworthiness or lending.
- **Privacy policy URL:**
  https://github.com/pawelmnowak1990-Now4czek/chilli/blob/main/docs/extension-privacy.md

## Expected review questions

Broad optional host permissions and `tabs` usually mean a longer, manual review. If the reviewer
asks, the answer is the host-permission justification above: the extension cannot know the user's
server address in advance and requests only that one origin at runtime. A short screen recording of
the options flow (enter address → Chrome asks for that one site → Test connection) helps.
