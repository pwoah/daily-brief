# Daily Brief

A personal news page built from public RSS feeds. No AI, no server: a GitHub Action runs `build.py` every morning at 6 am Pacific and publishes the result to GitHub Pages.

- **Change sources or sections:** edit `feeds.json` (any RSS or Atom feed works) and push.
- **Refresh now:** Actions tab → "Build Daily Brief" → Run workflow.
- **Build locally:** `python build.py`, then open `public/index.html`.
- **Look and feel:** `template.html`.

Note: GitHub pauses scheduled workflows in a repo with no activity for 60 days. If the page shows "not updated", open the Actions tab and re-enable the workflow.

## Daily email

`send_email.py` emails the brief to you after the 6 am run (and after manual "Run workflow" runs). It uses Gmail with no AI. To turn it on, add two secrets under Settings → Secrets and variables → Actions:

- `GMAIL_ADDRESS`: your Gmail address
- `GMAIL_APP_PASSWORD`: a Google App Password (needs 2-Step Verification). Never use your normal password.

Until both secrets exist, the email step just prints a note and skips.
