# Android

Chilli works with any phone: saving is one HTTPS request to `https://chilli.example.com/capture` with
your capture token. On Android the free, open-source app **HTTP Shortcuts** sends that request, and
Android's own share sheet hands it the screenshot or the link. Nothing else runs on the phone.

What you get:

- **Chilli: screenshot**: take a screenshot as usual, tap **Share** on the preview, pick **Chilli: screenshot**.
- **Chilli: link**: in any app (Chrome, X, YouTube, Reddit...), **Share** → **Chilli: link**.
- Optional **Chilli: text**: share selected text as a text save.

You need: the capture URL and the `CAPTURE_TOKEN` that `setup.sh` printed (also in `.env` on the
server: `grep '^CAPTURE_TOKEN=' .env`). Replace `chilli.example.com` with your domain (the host from
`PUBLIC_URL`). Setup takes about ten minutes.

> Menu names below are those of HTTP Shortcuts 3.x and stock Android. Phone makers rename some system
> screens (Samsung, Xiaomi), and the app's wording can change between versions; look for the closest match.

## 0. Check the token from a computer (optional, one minute)

This rules out server problems before you touch the phone:

```bash
read -rs TOKEN   # paste the capture token, then Enter (it is not shown)
curl -s -X POST https://chilli.example.com/capture \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.org"}'
```

The answer should be `{"id":"...","status":"accepted"}`. `missing token` or `wrong token` means the
token is wrong; fix that first.

## 1. Install HTTP Shortcuts

Install **HTTP Shortcuts** by Roland Meyer (rmy) from Google Play or F-Droid. Website and docs:
[http-shortcuts.rmy.ch](https://http-shortcuts.rmy.ch). It is free, without ads or an account.

## 2. "Chilli: screenshot"

In HTTP Shortcuts: **+** → **Regular Shortcut**. Name it **Chilli: screenshot** (pick any icon), then:

1. **Basic Request Settings**: Method **POST**, URL `https://chilli.example.com/capture`.
2. **Request Headers**: add one header, name `Authorization`, value `Bearer ` followed by the token
   (the word Bearer, one space, the token; no quotes).
3. **Request Body / Parameters**: Request Body Type **Parameters (form-data)**. Add a parameter of type
   **Single File** with the key `image`. Do not set a content type; the app sends the form itself.
4. **Response Handling**: On Success **Show a custom message**, message `Saved to Chilli`, Display Type
   **Toast Popup**. Leave On Failure on showing the response, so you see the server's message
   (for example `wrong token`).
5. **Trigger & Execution Settings** (Android 11 or newer): tick **Direct Share** (the option that lets
   the shortcut appear in the Direct Share row of the share sheet).
6. Save (the check mark at the top).

How it works: a shortcut with a file parameter accepts files from the share sheet. Android shares the
screenshot as a PNG or JPEG, which Chilli accepts (also WebP and HEIC, up to 15 MB by default).

### Use it

1. Take a screenshot (on most phones **Power + Volume down**).
2. On the preview that appears, tap **Share**.
3. Pick **Chilli: screenshot** in the Direct Share row, or **HTTP Shortcuts** ("Send to...") and then the shortcut.
4. Wait for the `Saved to Chilli` toast.

You can also share any image from the gallery the same way.

### Fewer taps for the screenshot itself

Android does not let an app take a screenshot by itself the way the iPhone Action Button does, so the
screenshot is taken by the system and then shared. To make that one gesture:

- **Pixel**: Settings → System → Gestures → **Quick Tap** → **Take screenshot** (double-tap the back of the phone).
- **Samsung**: Settings → Advanced features → Motions and gestures → **Palm swipe to capture**; or the
  Good Lock app's RegiStar module for a back tap.
- Most phones also have a **Screenshot** tile in Quick Settings and a three-finger swipe option under
  gestures.

## 3. "Chilli: link" in the share sheet

Shared text can contain quotes or line breaks (X shares "post text + link"), which would break a JSON
body typed by hand. A two-line script builds the JSON safely instead.

**First, two global variables.** In HTTP Shortcuts: menu (three dots) → **Variables** → **+**:

1. Type **Static Variable**, name `chilli_shared`, value empty, and tick
   **Allow Receiving Value from Share Dialog**. Save.
2. Type **Static Variable**, name `chilli_body`, value empty. Save.

**Then the shortcut.** Long-press **Chilli: screenshot** → **Duplicate**, rename the copy to
**Chilli: link** (the header with the token comes along), then:

1. **Request Body / Parameters**: Request Body Type **Custom Text**, Content Type `application/json`,
   and as the body only the variable `chilli_body`, inserted with the variable button (`{}`) above
   the text field. Nothing else in the body, not even quotes or braces.
2. **Scripting** → **Run before execution**:

   ```js
   // Wrap whatever was shared in valid JSON; Chilli picks the first https:// address out of it.
   setVariable('chilli_body', JSON.stringify({ url: getVariable('chilli_shared') }));
   ```

3. Response Handling and Direct Share stay as copied. Save.

### Use it

In Chrome: menu → **Share** → **Chilli: link** (or **HTTP Shortcuts** → **Chilli: link**). In X,
YouTube, Reddit and most apps: **Share** → the same. Chilli takes the first `https://...` address even
from text with extra words around it, and fetches the page or post itself.

If more than one shortcut uses `chilli_shared`, the app asks which one to run; that is expected once
you add the text shortcut below.

## 4. Optional: "Chilli: text" for selected text

Duplicate **Chilli: link**, rename it **Chilli: text**, and change only the script:

```js
setVariable('chilli_body', JSON.stringify({ text: getVariable('chilli_shared') }));
```

Select text in any app → **Share** → **Chilli: text**. It is saved as a text save (the same as
"Save selection" in the browser extension). If the shared text includes a link, use **Chilli: link**
instead: then Chilli reads the whole page.

## Alternative: Tasker or MacroDroid

If you already use Tasker or MacroDroid, their HTTP Request action can send the same requests:
`POST` to the capture URL with the `Authorization: Bearer <token>` header, and either a multipart form
with an `image` file field or a JSON body `{"url": "..."}`. Both apps can also trigger an HTTP
Shortcuts shortcut. This guide does not cover them step by step.

## Security

The token is stored in HTTP Shortcuts. Do not export or share these shortcuts with others (an export
contains the token). If it leaks: set a new `CAPTURE_TOKEN` in `.env`, run `docker compose up -d`, and
put the new token into the shortcuts' header and into the browser extension.

## Troubleshooting

- **`missing token` / `wrong token`** (401): check the header name `Authorization` and the value
  `Bearer <token>` with exactly one space; a token pasted with a trailing line break also fails.
- **"Chilli: screenshot" does not show up in the share sheet**: the shortcut needs the **Single File**
  parameter (step 2.3). Choose **HTTP Shortcuts** in the full share list; Direct Share rows can take a
  moment to appear after setup.
- **422 `no file in the image field`**: the file parameter's key is not exactly `image`.
- **415 `send a form with an image field or JSON with a url field`**: in the link shortcut the
  Content Type is not `application/json`.
- **422 with `url` in the message**: nothing that looks like `https://...` was shared. Use
  **Chilli: text** for plain text.
- **The script fails with an unknown variable**: create both `chilli_shared` and `chilli_body` (step 3);
  `getVariable` raises an error for a variable that does not exist.
- **Certificate errors**: use a real certificate (Caddy or certbot, as in the install guide); a
  self-signed one is rejected by Android unless you change the shortcut's Host Verification setting.
- Logs on the server (paths and status codes, no tokens): `docker compose logs --tail 20 api`.
