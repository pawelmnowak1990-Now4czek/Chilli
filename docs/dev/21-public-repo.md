# 21. Public repository (v0.1.0)

Chilli is published as a new public repository that starts from a single commit. The earlier
private repository, with the full step-by-step history, stays as an archive.

What was done:

- The tree of the private `main` was copied without its history and without `docs/handoffs/`
  (private working notes of one installation, now in `.gitignore`).
- Clone addresses in the README and the guides point to the public repository.
- `v0.1.0` is the first tag; `release.yml` builds the image and pushes it to GHCR.

Existing installations switch with `git remote set-url origin <new address>`, then
`git fetch origin && git reset --hard origin/main` once, because the new history is unrelated to the old one.
`.env` and the database are not touched by this.
