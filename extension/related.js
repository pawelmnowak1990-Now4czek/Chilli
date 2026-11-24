// The "You already have something on this" list: the same page and up to 3 related saves, with links to sources.
// The page gets the tab's address and title as parameters and asks the server itself (POST /related).
// Saves without an address (a screenshot without a link) have an id you can ask Claude about ("show save <id>").

const params = new URLSearchParams(location.search);
const pageUrl = params.get("url") || "";
const pageTitle = params.get("title") || "";
const content = document.getElementById("content");

document.getElementById("page").textContent = pageTitle ? `${pageTitle} (${pageUrl})` : pageUrl;

function item(save) {
  const li = document.createElement("li");
  const title = save.title || "(untitled)";
  if (save.url) {
    const link = document.createElement("a");
    link.href = save.url;
    link.textContent = title;
    li.append(link);
  } else {
    li.append(document.createTextNode(title));
  }
  const meta = document.createElement("div");
  meta.className = "meta";
  const date = (save.created_at || "").slice(0, 10);
  meta.append(document.createTextNode(`${date} · ${save.kind || save.source_type} · `));
  const id = document.createElement("code");
  id.textContent = save.id;
  meta.append(id);
  li.append(meta);
  return li;
}

function section(heading, saves) {
  const h2 = document.createElement("h2");
  h2.textContent = heading;
  const list = document.createElement("ul");
  saves.forEach((save) => list.append(item(save)));
  content.append(h2, list);
}

function showError(message) {
  content.innerHTML = "";
  const p = document.createElement("p");
  p.className = "error";
  p.textContent = message;
  content.append(p);
}

async function load() {
  const { server, token } = await chrome.storage.local.get({ server: "", token: "" });
  if (!server || !token) {
    showError("Set the server address and token in the extension options.");
    chrome.runtime.openOptionsPage();
    return;
  }
  // After an update the access to the server may not be granted yet (it is granted on Save in the options).
  let allowed = false;
  try {
    allowed = await chrome.permissions.contains({ origins: [`${new URL(server).origin}/*`] });
  } catch {
    // not a valid address: treated as no access
  }
  if (!allowed) {
    showError(`No access to ${server}: click Save in the extension options to allow it.`);
    chrome.runtime.openOptionsPage();
    return;
  }
  let result;
  try {
    const response = await fetch(`${server.replace(/\/+$/, "")}/related`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ url: pageUrl || null, title: pageTitle }),
    });
    if (!response.ok) throw new Error(`server answered ${response.status}`);
    result = await response.json();
  } catch (error) {
    showError(`Could not ask Chilli: ${error.message}`);
    return;
  }
  content.innerHTML = "";
  if (result.already_saved.length) section("This page is already saved", result.already_saved);
  if (result.related.length) section("Related saves", result.related);
  if (!result.already_saved.length && !result.related.length) {
    content.innerHTML = '<p class="empty">Nothing related in Chilli.</p>';
  }
}

load();
