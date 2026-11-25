// Renders story.html frame by frame into PNG files (see README.md in this folder).
// Usage: node render.js [fps] [output folder]
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const fps = Number(process.argv[2] || 30), dur = Number(process.env.DUR || 46.6), out = process.argv[3] || 'frames';
  fs.rmSync(out, { recursive: true, force: true }); fs.mkdirSync(out);
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1600, height: 900 } });
  await pg.goto('file://' + __dirname + '/story.html');
  await pg.waitForTimeout(300);
  const n = Math.round(dur * fps);
  for (let i = 0; i < n; i++) {
    await pg.evaluate(t => render(t), i / fps);
    await pg.screenshot({ path: `${out}/f${String(i).padStart(4, '0')}.png` });
  }
  await b.close();
})();
