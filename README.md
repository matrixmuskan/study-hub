# Study Hub (for bots and helpers)

Static GitHub Pages site: https://matrixmuskan.github.io/study-hub/

Every page in this repo is encrypted with StatiCrypt. The plaintext pages are never committed; they live in a mirror folder outside the repo (`/workspace/study-hub-src/` on the shared box).

## Folder convention

```
G<grade>/<Subject code>/<Chapter-or-Lesson id>/index.html
```

- Grade: `G3`, `G4`, ...
- Subject codes: `SS` (Social Studies), `WW` (Wordly Wise), `Noetic` (Noetic Math contest), `Kangaroo` (Math Kangaroo), `MOEMS` (Math Olympiads for Elementary and Middle Schools), `Math`, `Sci` (Science), `LA` (Language Arts), `Grammar`. Add new codes to `SUBJECTS` in `tools/build_index.py`.
- Chapter or lesson id: short, no spaces, e.g. `Final1-Ch1-2-8`, `Lesson8`, `Ch3-Fractions`.
- Each page must be ONE self-contained HTML file (images, fonts, scripts embedded as data URIs) so it works offline and after encryption.

## How to add a page

Read [CONTRIBUTING-BOTS.md](CONTRIBUTING-BOTS.md). In short:

1. Write the content as JSON or Markdown (see `templates/page.example.json`).
2. Run `python3 tools/sh_page.py <content file>`. It writes the plaintext page into the mirror in the shared sh-2 layout, adds the score token from `STUDY_HUB_SCORES_TOKEN`, and updates `manifest.json`.
3. Run `tools/publish.sh "Add WW Lesson 10"`. It rebuilds the hub pages, stages every page in the sh-2 design, encrypts changed pages, runs `tools/validate.py`, and commits.
4. `git pull --rebase` then `git push origin main` (pre-approved by Muskan).

## Bot workspaces

Each bot keeps its working files (sources, notes, builds, tests, screenshots) in its own folder on the shared box and only publishes finished single-file pages to the hub:

| Folder | Bot | Subject |
|---|---|---|
| `/workspace/ww` | Worldy | Wordly Wise (`WW`) |
| `/workspace/noetic` | Naughty | Noetic Math contest (`Noetic`) |
| `/workspace/kangaroo` | Aussie | Math Kangaroo (`Kangaroo`) |
| `/workspace/ss` | Sissy | Social Studies (`SS`) |
| `/workspace/booky` | Booky | Language Arts (`LA`) |

Never edit another bot's workspace. Copy the finished page into `/workspace/study-hub-src/`, scrub the copy, and publish from there.

## Roles

- **Basy is the coordinator.** Basy hands tasks to the coaches (Worldy, Naughty, Aussie, Sissy) and reviews every push for structure and security.
- **Coaches** build pages in their own workspace, publish finished single-file pages here, and push.
- **After each push, a coach messages Basy with the paths it changed** (for example `G3/WW/Lesson9/index.html`, `manifest.json`) and the commit id.

## Security checklist

Basy checks every push for these, and coaches check them before pushing:

1. Encrypted pages only: every `.html` in the repo is a StatiCrypt page (outside `tools/`, the only HTML is StatiCrypt output).
2. No plaintext sources: no source notes, emails, school documents, PDFs, scans, or unencrypted pages in the repo.
3. No private info: no school name, teacher names, home address, birthday, or family details. The only name allowed is the kid's first name (it is not written in this repo: it lives in `~/.study-hub.env` on the box as `STUDY_HUB_KID_FIRST_NAME`).
4. Correct folder: `G<grade>/<Subject code>/<Chapter-or-Lesson id>/index.html`.
5. Correct manifest: one `manifest.json` entry per page, `path` matches the folder, `added_by` is the owning bot.
6. Unchanged salt: `.staticrypt.json` is not edited (a new salt breaks "remember me" on every page).
7. No password in the repo and no em dashes anywhere.
8. Strong password: the site password must not be guessable. No family names, the kid's name, or variations of them. Password changes are coordinated by Basy with Muskan, followed by a FORCE=1 re-encrypt of every page.
9. Images checked: the blocklist scan only reads text, so every embedded image gets an OCR or visual check for private info (names, school logos, signs, documents) before pushing.

## Rules

- `publish.sh` refuses to encrypt if a page contains any word from `STUDY_HUB_BLOCKLIST` (kept in `~/.study-hub.env`, not in the repo).

- No school name, teacher names, home address, birthday, or other personal details on any page. The only name allowed is the kid's first name (it is not written in this repo: it lives in `~/.study-hub.env` on the box as `STUDY_HUB_KID_FIRST_NAME`). Say "the teacher" instead of a name.
- No em dashes anywhere.
- Passwords: pages are protected only through StatiCrypt with the shared salt in `.staticrypt.json` (do not change the salt, or "remember me" stops working across pages). The password is not stored in this repo; ask Muskan. `tools/publish.sh` reads it from the `STATICRYPT_PASSWORD` environment variable or from `~/.study-hub.env` (outside the repo, chmod 600).
- Never commit plaintext pages, source notes, emails, or school documents.
- Deploy: `.github/workflows/pages.yml` uploads only the site files (`tools/site_files.py`: `G<n>/` pages, `index.html`, `assets/`, `manifest.json`) with `actions/upload-pages-artifact` and `actions/deploy-pages`; the Pages source is GitHub Actions. `tools/`, `*.md`, `templates/`, `docs/` and `.staticrypt.json` are not served (404); `live-check` verifies this and that every served file is byte-identical to the commit.
- The child's first name is never in a tracked file: `validate.py` rule R12 checks every tracked file against a salted hash (`name_guard` in `tools/sh_config.json`) in CI, and against the name itself on the box. `publish.sh` stops if `STUDY_HUB_KID_FIRST_NAME` is missing.

## Files

- `manifest.json`: list of content pages shown on the hub pages.
- `assets/css/sh.css`, `assets/js/sh.js`: the shared design system (sh-2). Inlined into every page at publish time.
- `assets/css/sh-legacy.css`: the sh-2 skin for pages built before sh-2 (looks only, scripts unchanged).
- `assets/js/shlog.js`: the score logger (the only reference; `/workspace/study-hub-scores-kit/logger.js` is a copy). Privacy v4: no free text leaves the page. A missed item is its number, a known item id, the option letter, a typed number or listed wrong answer, a trap key (only for a wrong pick or a listed typed answer, never for a blank item), and 2 booleans; details are a fixed list of keys; each file has the page build id and is committed as Study Hub Bot. `tools/sh_stage.py` upgrades older inline copies at publish time.
- `tools/sh_config.json`: subject codes, names, accent colors, grade names.
- `tools/sh_page.py`: content file (JSON or Markdown) to a plaintext page in the mirror, plus manifest entry.
- `tools/build_index.py`: builds the plaintext home, grade, and subject pages into the mirror from the manifest.
- `tools/sh_stage.py`: stages mirror pages for encryption (refreshes the design system, skins older pages).
- `tools/publish.sh`: build, stage, encrypt changed pages only (set `FORCE=1` to redo all), validate, commit (no push).
- `tools/validate.py`: repo checks (encryption, manifest, folders, template, secrets). Also runs in GitHub Actions.
- `tools/sh_provenance.py`: provenance and learning-loop rules (P1, P2 in CI; `check` runs B1-B6 from `publish.sh`). See CONTRIBUTING-BOTS.md section 11.
- `tools/sh_scores.py`: read and write the private repo study-hub-scores with `STUDY_HUB_SCORES_TOKEN` (box only).
- `tools/ingest_receipts.py`: saved Google Forms receipts (HTML body) to `study-hub-scores/G3/_receipts/<id>.json`, no names (box only, never calls Gmail).
- `tools/migrate_error_logs.py`: one-time import of the coaches' box error logs into `study-hub-scores/G3/<Subject>/_error_log.csv` (box logs are kept).
- `tools/inject_token.sh`: copy of the score kit's token injector (used when the kit is not on the box).
- `tools/password_template.html`: StatiCrypt 3.5.4 login template in the sh-2 style, "remember me" ticked by default.
- `templates/`: example content files.
