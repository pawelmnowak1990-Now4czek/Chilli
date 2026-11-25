# Demo animation

The source of `docs/assets/demo.gif`: an animated story, not a screen recording. The answers in the chat
come from the demo data (`python -m app.demo_seed`), so they match what a real Chilli returns for it.

- `story.html`: the scenes. `render(t)` draws the frame for second `t`, so every frame is exact.
- `guy.js`: the character, drawn as SVG (pose, arms and facial expression as parameters).
- `render.js`: opens the page in Chromium (Playwright) and saves one PNG per frame.

Rebuild (needs Node with Playwright and ffmpeg):

```bash
cd docs/assets/demo
node render.js 30 frames
ffmpeg -framerate 30 -i frames/f%04d.png -vf "fps=12,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" ../demo.gif
ffmpeg -framerate 30 -i frames/f%04d.png -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart ../demo.mp4
rm -r frames
```

To preview a single moment, open `story.html?t=12` in a browser.
