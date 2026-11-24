// Chilli: extension background (service worker in Manifest V3).
//
// The extension has no capture logic of its own: it sends the same thing as the iPhone Shortcuts,
// to POST /capture on your server.
// - toolbar button: the selected text, or the page address when nothing is selected,
// - right-click menu: page, link, selection or a screenshot of the visible part of the tab,
// - keyboard shortcut Alt+Shift+S: tab screenshot.
// The result shows on the icon: a green ✓ or a red ! (details in the tooltip on hover).
//
// "You already have something on this": when a page opens, the extension asks the server
// (POST /related) for saves of the same page and up to 3 related ones. The number of related
// saves appears on the icon (orange), and a page that is already saved gets a blue dot. Titles
// show in the tooltip on the icon, and the "Related saves in Chilli" menu or Alt+Shift+R opens
// the list with links. Clicking the icon still saves in one move (no popup): zero friction.
//
// There is no default server: the address and token are set in the options page. Saving the
// options asks Chrome for access to that one server (optional_host_permissions in manifest.json).

// --- right-click menu ---------------------------------------------------------------------

chrome.runtime.onInstalled.addListener((details) => {
  // removeAll: after an extension update the menu from the previous version still exists.
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "page", title: "Save page to Chilli", contexts: ["page"] });
    chrome.contextMenus.create({ id: "link", title: "Save link to Chilli", contexts: ["link"] });
    chrome.contextMenus.create({ id: "selection", title: "Save selection to Chilli", contexts: ["selection"] });
    chrome.contextMenus.create({
      id: "screenshot",
      title: "Save tab screenshot to Chilli",
      contexts: ["page", "selection", "link", "image"],
    });
    chrome.contextMenus.create({ id: "related", title: "Related saves in Chilli", contexts: ["page", "selection"] });
  });
  // Fresh install: nothing works until the server is set, so show the options right away.
  if (details.reason === "install") chrome.runtime.openOptionsPage();
});

chrome.contextMenus.onClicked.addListener((info, clickedTab) => {
  // Just in case, the page address from the click itself, if the tab came without a URL.
  const tab = { ...clickedTab, url: (clickedTab && clickedTab.url) || info.pageUrl };
  if (info.menuItemId === "page") savePage(tab);
  else if (info.menuItemId === "link") saveLink(tab, info.linkUrl);
  else if (info.menuItemId === "selection") saveSelection(tab, info.selectionText);
  else if (info.menuItemId === "screenshot") saveScreenshot(tab);
  else if (info.menuItemId === "related") openRelatedPage(tab);
});

// --- toolbar button and keyboard shortcut ---------------------------------------------------

chrome.action.onClicked.addListener(async (tab) => {
  const selected = await readSelection(tab);
  if (selected) await saveSelection(tab, selected);
  else await savePage(tab);
});

chrome.commands.onCommand.addListener((command, tab) => {
  if (command === "save-screenshot") saveScreenshot(tab);
  else if (command === "show-related") openRelatedPage(tab);
});

// --- "You already have something on this" ---------------------------------------------------

// Results for recently checked addresses. The service worker gets put to sleep at times and this
// memory is lost, which does no harm: at worst we ask the server again.
const relatedCache = new Map();
const CACHE_MS = 10 * 60 * 1000;

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    refreshRelated(await chrome.tabs.get(tabId));
  } catch {
    // the tab was closed in the meantime
  }
});

// Tabs with a save error: the red ! stays until the tab moves to another page, the tooltip does not cover it.
const errorTabs = new Set();
// Sites like X and LinkedIn change the address without reloading (history.pushState) and set the
// title only a moment later. So we also react to title changes, with a short delay, so that several
// changes in a row produce one request to the server, with the final title.
const pendingRefresh = new Map();

chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.url) errorTabs.delete(tabId);
  if (!tab.active || !(change.status === "complete" || change.title || change.url)) return;
  clearTimeout(pendingRefresh.get(tabId));
  pendingRefresh.set(tabId, setTimeout(() => {
    pendingRefresh.delete(tabId);
    chrome.tabs.get(tabId).then(refreshRelated, () => {});
  }, 800));
});

async function shouldLookUp(tab) {
  const { server, token, related } = await getConfig();
  // No server or token yet: stay quiet. This runs on every tab change, so it must not open the options.
  if (!server || !token || !related || !tab || tab.incognito || !isWebUrl(tab.url)) return false;
  if (tab.url.startsWith(server)) return false; // we do not check our own server
  return hasServerAccess(server);
}

async function fetchRelated(url, title) {
  const cached = relatedCache.get(url);
  if (cached && Date.now() - cached.at < CACHE_MS) return cached.result;
  const { server, token } = await getConfig();
  if (!server || !token) return null;
  const response = await fetch(`${server}/related`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    // Address and title in the request body, not in the URL: they will not end up in server logs.
    body: JSON.stringify({ url, title }),
  });
  if (!response.ok) return null;
  const result = await response.json();
  relatedCache.set(url, { at: Date.now(), result });
  return result;
}

async function refreshRelated(tab) {
  if (!(await shouldLookUp(tab))) return;
  let result;
  try {
    result = await fetchRelated(tab.url, tab.title || "");
  } catch {
    return; // no network: the icon stays without hints, saving still works
  }
  if (!result || errorTabs.has(tab.id)) return;
  // The response came when the tab was already on another page: we do not show stale hints.
  let current;
  try {
    current = await chrome.tabs.get(tab.id);
  } catch {
    return;
  }
  if (current.url !== tab.url) return;
  await showRelatedBadge(tab.id, result);
}

async function showRelatedBadge(tabId, result) {
  const saved = result.already_saved.length;
  const related = result.related.length;
  const lines = [];
  if (saved) lines.push("This page is already in Chilli.");
  if (related) lines.push("Related in Chilli:", ...result.related.map((r) => `• ${r.title || r.url}`));
  if (!lines.length) {
    await chrome.action.setBadgeText({ tabId, text: "" });
    await chrome.action.setTitle({ tabId, title: "Save to Chilli (selection or page)" });
    return;
  }
  lines.push("", "Click to save. Alt+Shift+R: list of related saves.");
  await chrome.action.setBadgeBackgroundColor({ tabId, color: related ? "#e07a1f" : "#2f6fd6" });
  await chrome.action.setBadgeText({ tabId, text: related ? String(related) : "●" });
  await chrome.action.setTitle({ tabId, title: lines.join("\n") });
}

function openRelatedPage(tab) {
  const params = new URLSearchParams({ url: tab.url || "", title: tab.title || "" });
  chrome.tabs.create({ url: `related.html?${params}` });
}

// --- what we send ---------------------------------------------------------------------------

async function savePage(tab) {
  return send(tab, JSON.stringify({ url: tab.url }), "application/json", "page");
}

async function saveLink(tab, linkUrl) {
  return send(tab, JSON.stringify({ url: linkUrl }), "application/json", "link");
}

async function saveSelection(tab, fallbackText) {
  // Chrome joins the menu text (info.selectionText) into one line; from the page we read it with
  // paragraph breaks. When the page does not allow that (e.g. the Chrome Web Store), the menu version stays.
  const text = (await readSelection(tab)) || fallbackText || "";
  if (!text.trim()) return showResult(tab, false, "Nothing is selected");
  const body = { text, url: isWebUrl(tab.url) ? tab.url : null, title: tab.title || null };
  return send(tab, JSON.stringify(body), "application/json", "selection");
}

async function saveScreenshot(tab) {
  let dataUrl;
  try {
    // Screenshot of the visible part of the active tab. The click grants the permission (activeTab).
    dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
  } catch (error) {
    return showResult(tab, false, `Cannot take a screenshot of this tab: ${error.message}`);
  }
  const image = await (await fetch(dataUrl)).blob();
  const form = new FormData();
  form.append("image", image, "screenshot.png");
  // The full page address: the server will fetch the whole article text, not just what the screenshot shows.
  if (isWebUrl(tab.url)) form.append("url", tab.url);
  return send(tab, form, null, "screenshot");
}

// --- helpers --------------------------------------------------------------------------------

async function readSelection(tab) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });
    return (result && result.result) || "";
  } catch {
    return ""; // chrome:// pages, the Chrome Web Store, PDFs: no access to the content
  }
}

function isWebUrl(url) {
  return typeof url === "string" && /^https?:\/\//.test(url);
}

async function getConfig() {
  const stored = await chrome.storage.local.get({ server: "", token: "", related: true });
  return { server: stored.server.replace(/\/+$/, ""), token: stored.token, related: stored.related };
}

// Whether Chrome lets the extension talk to the server (granted when the options are saved).
async function hasServerAccess(server) {
  try {
    return await chrome.permissions.contains({ origins: [`${new URL(server).origin}/*`] });
  } catch {
    return false; // not a valid address
  }
}

// Sends a save to /capture. contentType = null for a form: the browser sets
// multipart/form-data itself, together with the boundary between fields.
async function send(tab, body, contentType, label) {
  const { server, token } = await getConfig();
  if (!server || !token) {
    chrome.runtime.openOptionsPage();
    return showResult(tab, false, "Set the server address and token in the extension options");
  }
  if (!(await hasServerAccess(server))) {
    chrome.runtime.openOptionsPage();
    return showResult(tab, false, `No access to ${server}: click Save in the extension options to allow it`);
  }
  const headers = { Authorization: `Bearer ${token}` };
  if (contentType) headers["Content-Type"] = contentType;

  try {
    const response = await fetch(`${server}/capture`, { method: "POST", headers, body });
    if (response.status === 202) return showResult(tab, true, `Saved to Chilli (${label})`);
    if (response.status === 401) {
      chrome.runtime.openOptionsPage();
      return showResult(tab, false, "Wrong token: fix it in the options");
    }
    const detail = await response.text();
    return showResult(tab, false, `Chilli rejected the save (${response.status}): ${detail.slice(0, 200)}`);
  } catch (error) {
    return showResult(tab, false, `No connection to ${server}: ${error.message}`);
  }
}

async function showResult(tab, ok, message) {
  const tabId = tab && tab.id;
  if (ok) errorTabs.delete(tabId);
  else errorTabs.add(tabId);
  await chrome.action.setBadgeBackgroundColor({ tabId, color: ok ? "#2e8b3c" : "#d62828" });
  await chrome.action.setBadgeText({ tabId, text: ok ? "✓" : "!" });
  await chrome.action.setTitle({ tabId, title: message });
  // The green mark disappears after a moment; the red one stays so the error does not slip by unnoticed.
  // After a save the page is in Chilli, so we check related saves again (without the cache).
  if (ok) {
    setTimeout(async () => {
      await chrome.action.setBadgeText({ tabId, text: "" });
      if (tab && tab.url) relatedCache.delete(tab.url);
      if (tab) refreshRelated(tab);
    }, 3000);
  }
  return { ok, message };
}
