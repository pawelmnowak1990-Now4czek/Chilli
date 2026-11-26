# Chilli browser extension: privacy policy

Last updated: 2026-11-26

The Chilli extension is part of [Chilli](https://github.com/pawelmnowak1990-Now4czek/chilli), a free,
open-source, self-hosted knowledge base. It has no backend of its own: it talks only to the Chilli
server that **you** run and whose address **you** enter in the extension's options. The authors of the
extension never receive any data from it.

## What the extension sends, and where

Everything goes to one place: the server address you set in the options, over the connection you
configured (HTTPS in a normal setup). Nothing is sent before you set that address and grant the
browser permission for it.

| When | What is sent to your server |
| --- | --- |
| You click the toolbar icon, a "Save ... to Chilli" menu item, or press Alt+Shift+S | the page address and title; the selected text, the link or a screenshot of the visible part of the tab, depending on what you chose |
| A page opens, while "Show what I already have" is on (the default; it can be turned off in the options) | the page address and title, to ask your server for related saves. Incognito tabs and your own server's pages are skipped. |
| You click "Test connection" in the options | an empty test request with your token |

What your server does with a save (describing it with the AI model you configured, storing it in your
database) is set by you on that server; see the Chilli README, section "Privacy".

## What the extension stores

In the browser's local extension storage (`chrome.storage.local`, not synced to other devices): the
server address, the capture token and the on/off setting for related saves. Nothing else, no history
of pages or saves. Removing the extension deletes them.

## What the extension does not do

- No analytics, telemetry, advertising or tracking of any kind.
- No data is sold, shared with or transferred to third parties.
- No remote code: all code ships inside the extension and is open source.
- No access to sites in advance: host access is requested only for your own server address
  (`optional_host_permissions`); reading a page's selection or taking a screenshot happens only on
  the tab where you used the extension.

## Permissions and why they are needed

| Permission | Why |
| --- | --- |
| `contextMenus` | the "Save ... to Chilli" and "Related saves in Chilli" right-click items |
| `activeTab`, `scripting` | read the selected text and take a screenshot of the tab you are saving, only when you ask |
| `tabs` | read the address and title of the open page, for saving and for the related-saves count on the icon |
| `storage` | keep the server address, token and setting |
| optional host access (`https://*/*`, `http://localhost/*`, `http://127.0.0.1/*`) | requested for the one server address you enter, because every Chilli user runs their own server at their own address |

## Contact

Questions or concerns: open an issue at
<https://github.com/pawelmnowak1990-Now4czek/chilli/issues>.
