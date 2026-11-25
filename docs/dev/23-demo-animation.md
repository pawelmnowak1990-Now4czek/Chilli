# 23. Demo animation

What was built: `docs/assets/demo.gif`, an animated story for the top of the README, instead of a screen
recording (no real saves on screen, and it can be changed and rebuilt in minutes).

The story, about 47 seconds:

1. On the couch: a post about a self-watering planter, the Action Button, "Saved to Chilli".
2. A link: an article in the browser, Share, Chilli in the share sheet, "Link saved to Chilli".
3. The server describes the save and rates it for a project.
4. Three weeks later, four questions to an AI client: a search, `top_saves` for a project,
   `from_archive`, and a reminder. The answers are the demo data from `app/demo_seed.py`.
5. The tomatoes survived; the end card with the repository address.

The chat window is a generic "AI assistant", not a copy of any product, and the README says that the
GIF is an illustration.

How to run: `docs/assets/demo/README.md` (Node with Playwright, then ffmpeg). The same frames also give
an MP4 for social media.
