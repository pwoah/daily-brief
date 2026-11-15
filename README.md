# Daily Brief

A personal news page built from public RSS feeds. No AI, no server: a GitHub Action runs `build.py` every morning at 6 am Pacific and publishes the result to GitHub Pages.

- **Change sources or sections:** edit `feeds.json` (any RSS or Atom feed works) and push.
- **Refresh now:** Actions tab → "Build Daily Brief" → Run workflow.
- **Build locally:** `python build.py`, then open `public/index.html`.
- **Look and feel:** `template.html`.

Note: GitHub pauses scheduled workflows in a repo with no activity for 60 days. If the page shows "not updated", open the Actions tab and re-enable the workflow.
