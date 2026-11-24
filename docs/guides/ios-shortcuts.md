# iPhone Shortcuts

Two Shortcuts send everything to Chilli. The phone holds no logic: the Shortcuts only post the
screenshot or the link to `https://chilli.example.com/capture` with your capture token.

You need: the capture URL and the `CAPTURE_TOKEN` that `setup.sh` printed (also in `.env` on the
server: `grep '^CAPTURE_TOKEN=' .env`). Replace `chilli.example.com` with your domain (the host
from `PUBLIC_URL`).

> **TODO (maintainer):** an importable iCloud link for both Shortcuts will be added here. Until then,
> build them by hand as below; it takes about five minutes.

## 1. "Chilli: screenshot" on the Action Button

In the Shortcuts app: **+** (new shortcut), name it **Chilli: screenshot**, then add these actions:

1. **Take Screenshot**.
2. **Get Contents of URL**:
   - URL: `https://chilli.example.com/capture`
   - tap the arrow to show more options,
   - Method: **POST**,
   - Headers: add one, key `Authorization`, value `Bearer ` followed by the token
     (the word Bearer, one space, the token; no quotes),
   - Request Body: **Form**; add a field of type **File**, key `image`, value: the **Screenshot**
     variable from step 1.
3. **If**: input **Contents of URL** (tap it → Type → **Text**), condition **contains**, text `accepted`.
   - In the If branch: **Show Notification** with the text `Saved to Chilli`.
   - In the Otherwise branch: **Show Alert** with **Contents of URL**, so you see the server's message
     (for example a wrong or missing token).

Why the If: Shortcuts do not stop on an HTTP error, they just return the answer. A successful save
answers `202` with `{"id": "...", "status": "accepted"}`; errors answer `{"detail": "..."}`, and no
error message contains the word `accepted`. (Before version 0.1 the success word was `przyjęty`; a
Shortcut built for that needs its If changed to `accepted`.)

### Put it on a button

- iPhone with an Action Button: Settings → Action Button → swipe to **Shortcut** → **Chilli: screenshot**.
- Without one: Settings → Accessibility → Touch → **Back Tap** → Double Tap → **Chilli: screenshot**.

On the first run iOS asks whether the Shortcut may connect to your domain: choose **Always Allow**,
otherwise it asks on every save.

### Optional: the page address with a Safari screenshot

You can add **Get URLs from Screen** (before Get Contents of URL) and a **Text** field `url` in the
form. Chilli then fetches the full page text in addition to the screenshot. In practice iOS often
gives only the domain for Safari pages, and Chilli ignores a bare domain; the share-sheet Shortcut
below gives the exact link.

## 2. "Chilli: link" in the share sheet

1. In the Shortcuts list, long-press **Chilli: screenshot** → **Duplicate**, rename the copy to
   **Chilli: link** (the header with the token comes along).
2. Remove the **Take Screenshot** action.
3. Tap the (i) details button → turn on **Show in Share Sheet**. In "Receive ... from Share Sheet"
   select **all types** (with URLs only, some apps such as X hand over nothing). Set
   "If there's no input" to **Stop**.
4. In **Get Contents of URL**: Request Body **JSON**, remove the `image` field, add a field of type
   **Text**, key `url`, value **Shortcut Input**.
5. The If and the notification stay as they are.

Test: in Safari, Share → **Chilli: link**. If it is missing, scroll the share sheet and use **Edit Actions**.
In X use "Share via..." to reach the system share sheet. Chilli takes the first `https://...` address
even from text with extra words around it.

## Security

The token is stored inside the Shortcuts. Do not share these Shortcuts (an exported Shortcut contains
the token). If it leaks: set a new `CAPTURE_TOKEN` in `.env`, run `docker compose up -d`, and put the
new token into both Shortcuts and the extension.

## Troubleshooting

- **400 Bad Request from the web server**: usually an invisible line break pasted into the header value.
  Delete the header, add it again, type the key by hand, paste the token and check its end.
- **"Cannot convert from Dictionary to URL"** in the If action: tap the Contents of URL variable in
  the If → Type → **Text**.
- In the `image` field only Clipboard, Current Date and similar are offered: the **Take Screenshot**
  action is missing above Get Contents of URL. Do not use "Shortcut Input" here; with the Action Button it is empty.
- **422 "input is empty"** from the link Shortcut: in its details, receive **all types** from the share sheet.
- Logs on the server (paths and status codes, no tokens): `docker compose logs --tail 20 api`.
