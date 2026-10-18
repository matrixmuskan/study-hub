# Krishiv's Study Hub (for bots and helpers)

Static GitHub Pages site: https://matrixmuskan.github.io/study-hub/

Every page in this repo is encrypted with StatiCrypt. The plaintext pages are never committed; they live in a mirror folder outside the repo (`/workspace/study-hub-src/` on the shared box).

## Folder convention

```
G<grade>/<Subject code>/<Chapter-or-Lesson id>/index.html
```

- Grade: `G3`, `G4`, ...
- Subject codes: `SS` (Social Studies), `WW` (Wordly Wise), `Math`, `Sci` (Science), `LA` (Language Arts), `Grammar`. Add new codes to `SUBJECTS` in `tools/build_index.py`.
- Chapter or lesson id: short, no spaces, e.g. `Final1-Ch1-2-8`, `Lesson8`, `Ch3-Fractions`.
- Each page must be ONE self-contained HTML file (images, fonts, scripts embedded as data URIs) so it works offline and after encryption.

## How to add a page

1. Put the plaintext page at `/workspace/study-hub-src/G3/WW/Lesson9/index.html` (same path it will have in the repo).
2. Add an entry to `manifest.json` (repo root):
   ```json
   {"grade": "G3", "subject": "WW", "title": "Lesson 9 words", "path": "G3/WW/Lesson9/", "test_date": "2026-10-29", "added_by": "Worldy"}
   ```
3. Run `tools/publish.sh "Add WW Lesson 9"`. It rebuilds the home page from the manifest, encrypts every page from the mirror into the repo, checks nothing is left in plaintext, and commits.
4. `git push origin main` (only when the person running the task has approved pushing).

## Rules

- `publish.sh` refuses to encrypt if a page contains any word from `STUDY_HUB_BLOCKLIST` (kept in `~/.study-hub.env`, not in the repo).

- No school name, teacher names, home address, birthday, or other personal details on any page. The only name allowed is the kid's first name, Krishiv. Say "the teacher" instead of a name.
- No em dashes anywhere.
- Passwords: pages are protected only through StatiCrypt with the shared salt in `.staticrypt.json` (do not change the salt, or "remember me" stops working across pages). The password is not stored in this repo; ask Muskan. `tools/publish.sh` reads it from the `STATICRYPT_PASSWORD` environment variable or from `~/.study-hub.env` (outside the repo, chmod 600).
- Never commit plaintext pages, source notes, emails, or school documents.
- `.nojekyll` must stay so GitHub Pages serves files as-is.

## Files

- `manifest.json`: list of pages shown on the home page.
- `tools/build_index.py`: builds the plaintext home page into the mirror from the manifest.
- `tools/publish.sh`: build, encrypt, commit (no push).
- `tools/password_template.html`: StatiCrypt 3.5.4 login template with "remember me" ticked by default.
