# Cortex Website

A static site that consumes `.cc-marketspec/dist/manifest.json` plus
`CHANGELOG.md`. The manifest is generated from the native Claude Code plugin
metadata and the authored `.cc-marketspec/` presentation overlays.

## Build

```bash
npm ci
npx --no-install cc-marketspec
node site/build.mjs
```

Output goes to `site/dist/` (gitignored). The site renderer itself uses only
Node built-ins; cc-marketspec is a build-time dev dependency.

## Tests

```bash
node --test site/tests/*.test.mjs
```

## Deployment (Cloudflare Pages)

Handled by Cloudflare Pages' **Git integration** — CF connects to this repo
and builds + publishes on its own infrastructure after each push. GitHub
Actions doesn't deploy; it validates the marketplace data and runs tests plus
a smoke build as a quality gate.

One-time setup (in the Cloudflare dashboard):

1. Workers & Pages → Create → Pages → **Connect to Git**, authorize and
   select `XBlueSky/cortexes`.
2. Build settings:
   - **Production branch**: `plugin`
   - **Framework preset**: None
   - **Build command**: `npm ci && npx --no-install cc-marketspec && node site/build.mjs`
   - **Build output directory**: `site/dist`
   - **Root directory**: leave blank
3. Save and Deploy.

After this, pushes to `plugin` deploy to production, and other
branches/PRs get preview deployments. No API token or GitHub secret needed.
