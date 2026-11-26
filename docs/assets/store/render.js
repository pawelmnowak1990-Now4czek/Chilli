// Renders the Chrome Web Store images from store.html: node render.js
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const browser = await chromium.launch();
  const shots = [["save", 1280, 800], ["related", 1280, 800], ["options", 1280, 800], ["tile", 440, 280]];
  for (const [s, w, h] of shots) {
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    await page.goto("file://" + path.join(__dirname, "store.html") + "?s=" + s);
    await page.waitForTimeout(300);
    const name = s === "tile" ? "promo-tile-440x280.png" : `screenshot-${s}-1280x800.png`;
    await page.screenshot({ path: path.join(__dirname, name) });
  }
  await browser.close();
})();
