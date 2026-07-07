# Cortex Website

A static site with `manifest.json` + `CHANGELOG.md` as the single source of
truth.

## Build

    node site/build.mjs

Output goes to `site/dist/` (gitignored). Zero npm dependencies, Node
built-ins only.

## Tests

    node --test site/tests/*.test.mjs

## Deployment (Cloudflare Pages)

Handled by Cloudflare Pages' **Git integration** — CF connects to this repo
and builds + publishes on its own infrastructure after each push. GitHub
Actions doesn't deploy; it only runs tests + a smoke build as a quality gate.

One-time setup (in the Cloudflare dashboard):

1. Workers & Pages → Create → Pages → **Connect to Git**, authorize and
   select `XBlueSky/cortexes`.
2. Build settings:
   - **Production branch**: `plugin`
   - **Framework preset**: None
   - **Build command**: `node site/build.mjs`
   - **Build output directory**: `site/dist`
   - **Root directory**: leave blank
3. Save and Deploy.

After this, pushes to `plugin` deploy to production, and other
branches/PRs get preview deployments. No API token or GitHub secret needed.
