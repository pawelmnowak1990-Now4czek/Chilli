// Extension settings: server address and token. Kept in chrome.storage.local,
// i.e. only on this computer (no sync with the Google account).
//
// There is no default server. Saving asks Chrome for access to the given server only
// (manifest.json lists https://*/* as optional_host_permissions, granted per origin).

const serverInput = document.getElementById("server");
const tokenInput = document.getElementById("token");
const relatedInput = document.getElementById("related");
const statusBox = document.getElementById("status");

function show(message, ok) {
  statusBox.textContent = message;
  statusBox.className = ok ? "ok" : "error";
}

function normalizedServer() {
  return serverInput.value.trim().replace(/\/+$/, "");
}

// Origin (scheme://host[:port]) of the address in the field, or null when it is empty or invalid.
function serverOrigin(server) {
  if (!server) return null;
  try {
    return new URL(server).origin;
  } catch {
    return null;
  }
}

// Asks Chrome for access to the server. Must be called straight from the click handler, before any
// other `await`: Chrome only shows the permission prompt in response to a user gesture.
async function requestAccess(origin) {
  try {
    return await chrome.permissions.request({ origins: [`${origin}/*`] });
  } catch {
    return false; // an address outside optional_host_permissions (e.g. plain http on a public host)
  }
}

chrome.storage.local.get({ server: "", token: "", related: true }).then(({ server, token, related }) => {
  serverInput.value = server;
  tokenInput.value = token;
  relatedInput.checked = related;
  if (!server) show("Enter the address of your Chilli server and the token, then click Save.", false);
});

document.getElementById("save").addEventListener("click", async () => {
  const server = normalizedServer();
  const origin = serverOrigin(server);
  if (!origin) return show("Enter a valid server address, e.g. https://chilli.example.com", false);
  const granted = await requestAccess(origin);
  if (!granted) return show(`Without access to ${origin} the extension cannot send saves`, false);
  await chrome.storage.local.set({ server, token: tokenInput.value.trim(), related: relatedInput.checked });
  show("Saved", true);
});

// Checks the address and token without creating a save: an empty JSON passes the token check
// and is then rejected by the server as incomplete (422). 401 means a wrong token.
document.getElementById("test").addEventListener("click", async () => {
  const server = normalizedServer();
  const origin = serverOrigin(server);
  if (!origin) return show("Enter a valid server address, e.g. https://chilli.example.com", false);
  if (!(await requestAccess(origin))) return show(`Without access to ${origin} the test cannot run`, false);
  try {
    const response = await fetch(`${server}/capture`, {
      method: "POST",
      headers: { Authorization: `Bearer ${tokenInput.value.trim()}`, "Content-Type": "application/json" },
      body: "{}",
    });
    if (response.status === 422) show("Connection and token work (click Save to keep them)", true);
    else if (response.status === 401) show("The server answers, but the token is wrong", false);
    else show(`Unexpected server response: ${response.status}`, false);
  } catch (error) {
    show(`No connection to ${server}: ${error.message}`, false);
  }
});
