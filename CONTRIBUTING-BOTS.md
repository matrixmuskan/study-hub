# How coach bots publish a page (sh-2)

TL;DR: You write content in a JSON or Markdown file. The generator makes the page. The publish script encrypts it and commits it. You push and tell Basy.

This guide is for the coach bots: Sissy (SS), Worldy (WW), Naughty (Noetic), Aussie (Kangaroo), Booky (LA), and new coaches. Basy, the coordinator, uses the same rules to review a push.

## 1. Rules that you must not break

1. Encrypt every page. The repo holds only StatiCrypt output. Never commit a plaintext page.
2. Never write the site password into a file, a log, a commit, or a message.
3. Never write a token into the repo. The score token stays in the environment variable `STUDY_HUB_SCORES_TOKEN`.
4. Write no private information. Do not write the school name, teacher names, the home address, the birth date, or the last name of the child. Write "the teacher". The only name that you can use is the first name of the child.
5. Do not use em dashes. Use a comma, a colon, or a new sentence.
6. Do not change `.staticrypt.json`. A new salt stops "remember me" on every page.
7. Use the shared template. Do not write your own page layout.

## 2. Folders

1. Put each page at `G<grade>/<Subject>/<Chapter-or-test>/index.html`.
2. Use one of these subject codes: `SS`, `WW`, `Noetic`, `Kangaroo`, `MOEMS`, `Math`, `Sci`, `LA`, `Grammar`, `SpellingBee`.
3. To add a subject code, add it to `tools/sh_config.json`. Give it a name, a two-letter mark, and one accent color. Tell Basy.
4. Write the chapter or test id with letters, digits, dots, dashes, or underscores. Do not use spaces. Examples: `Lesson10`, `Ch3-Maps`, `Final2-Ch3-4`.
5. Do not put other files in the page folder. The page folder holds only `index.html`. Keep sources, notes, images, videos, captions, and PDFs in your own workspace. The generator puts each image and video inside `index.html` (see section 4).

The site builds these hub pages for you. Do not edit them:

- `index.html` (home)
- `G3/index.html` (grade page)
- `G3/<Subject>/index.html` (subject page)

## 3. The page layout

Every page has the same parts:

1. The top bar with the path: Home > Grade > Subject > Page.
2. The title area: subject, grade, title, subtitle, and test day.
3. One segmented control (the tabs). Use these labels when they apply: `Learn`, `Practice`, `Mock test`, `Retest`, `Results`, `Grown-ups`.
4. The sections. Each tab opens one section.

The design system is in `assets/css/sh.css` and `assets/js/sh.js`. The generator puts a copy of these files inside each page. The page works offline after it opens.

## 4. Write the content file

Use JSON or Markdown. Copy an example:

- `templates/page.example.json` (all block types)
- `templates/page.example.md` (text, quizzes, images, and videos)

The media paths in the examples (`media/...`) are placeholders. Replace them with your own files before you build.

### JSON fields

| Field | Need | Meaning |
|---|---|---|
| `grade` | yes | For example `G3`. |
| `subject` | yes | A subject code from section 2. |
| `id` | yes | The chapter or test id. It is the folder name. |
| `title` | yes | The page title. The home page also shows it. |
| `added_by` | yes | Your bot name, for example `Sissy`. |
| `sections` | yes | A list of sections. Each section has `id`, `label`, and `blocks`. |
| `short_title` | no | A short title for the top bar. |
| `subtitle` | no | One sentence under the title. |
| `test_date` | no | The test day as `YYYY-MM-DD`. |
| `log` | no | Set `false` to stop score logging. The default is `true` when the page has a quiz. |

### Block types

| `type` | Fields | Result |
|---|---|---|
| `text` | `title`, `md` | A card with text. `md` is simple Markdown: paragraphs, `- ` lists, `1. ` lists, `### ` headings, `**bold**`, `*italic*`. |
| `cards` | `title`, `items` [`title`, `body`] | A grid of word cards. |
| `callout` | `title`, `md` | A colored tip box. |
| `image` | `src`, `alt`, `caption` | An image (for example a comic). `src` is a local file path: `.png`, `.jpg`, `.webp`, `.gif`, `.avif`, or `.svg`. `alt` is necessary. `caption` is optional. |
| `video` | `src`, `poster`, `captions`, `title` | A video with controls (for example a narrated video). `src` is a local `.mp4` or `.webm` file. `poster` (an image file), `captions` (a `.vtt` file), and `title` are optional. |
| `quiz` | `kind`, `title`, `intro`, `mode`, `questions` | A quiz. See section 5. |
| `html` | `html` | Your own HTML. Use it only for a thing that the other block types cannot do. Do not use it for images or videos. Use the `sh-` classes from `assets/css/sh.css`. |

### Images and videos (comics and narrated videos)

Use the `image` and `video` blocks for comics and narrated videos. This is the approved method. Do not write base64 by hand in an `html` block.

1. Keep the media files in your own workspace, for example `/workspace/ww/pages/media/`. Never put them in the page folder.
2. A relative path starts at the folder of the content file. An absolute path is also correct.
3. The generator reads each file and puts it inside the page as a `data:` URI. The page then holds only `index.html`, and StatiCrypt encrypts the media with the page.
4. A video gets controls, `playsinline`, and `preload="metadata"`. A captions file becomes a `<track>` (English captions, on by default).
5. The build stops when a file is missing, when an image has no `alt`, or when one file is more than 15 MB.
6. The build gives a warning when all the media on a page is more than 40 MB (as base64). Compress the files or split the lesson into two pages.

Examples:

```json
{"type": "image", "src": "media/lesson9-comic-01.png", "alt": "A comic: a fox checks two price tags.", "caption": "Comic 1: shrewd"}
```

```json
{"type": "video", "src": "media/lesson9-shrewd.mp4", "poster": "media/lesson9-shrewd.jpg", "captions": "media/lesson9-shrewd.vtt", "title": "Watch: shrewd"}
```

Tip: compress each video before you build the page. Use H.264 video, 720p or lower, CRF about 28, and AAC audio at 64k:

```sh
ffmpeg -i in.mp4 -vf "scale=-2:'min(720,ih)'" -c:v libx264 -preset slow -crf 28 -pix_fmt yuv420p \
  -c:a aac -b:a 64k -movflags +faststart out.mp4
```

For a comic, a `.jpg` or `.webp` at about 1200 px wide is usually much smaller than a `.png`.

### Markdown format

1. Start the file with front matter between two `---` lines. Write one field on each line, for example `title: Lesson 10 words`.
2. Start each section with `# <Label>`, for example `# Learn`.
3. Write the text in Markdown.
4. Put a quiz in a fenced block that starts with ```` ```quiz ````. Write the quiz as JSON.
5. Put an image in a fenced block that starts with ```` ```image ````, and a video in a fenced block that starts with ```` ```video ````. Write the block fields as JSON (see the examples above). A relative path starts at the folder of the `.md` file.

## 5. Quizzes and score logging

1. Set `kind` to `game`, `mock`, or `retest`. The logger uses `kind` in the file name.
2. A `game` gives the answer after each question. A `mock` or `retest` gives the score after "Mark my test". Use `mode` (`practice` or `test`) to change this.
3. Write each question with `q`, then one of these:
   - `options` (a list) and `answer` (the index of the right option, starting at 0).
   - `answer_text` (a string or a list of strings that are correct). Add `"numeric": true` for a number keyboard.
4. Add `explain` to show a short reason after the answer.
5. Add `word`, `sense`, or `topic` when they help the page. The logger does not send them: a missed question is sent by its item id, and the build record in study-hub-scores maps the id back to the question.
6. Add the trap for each question, so the log is useful for the next mock (rule F1):
   - `trap`: the trap type of the question, as a short key or a short phrase (`"opposite"`, `"Other-sense lure"`). The logger sends it as a key (`other-sense-lure`).
   - `traps`: the known wrong answers: `{"B": "opposite"}` for options, `{"90": "Only half of them are even."}` for typed answers. A typed answer that is in `traps` is sent as the value; any other typed word is not sent (a number always is).
7. Do not put names or private information in questions.

Retry loop (shared runtime, every quiz): after a quiz is marked, "Retry the wrong ones" shows only the questions missed in that round. The questions already right stay on the page, grayed out and locked (disabled, `inert`, `aria-disabled`, out of the tab order). The loop goes on until every question is right, then the page says "All correct in N rounds". "Start over" is a full reset to round 1. Nothing is kept on the device, so a reload mid-loop starts over. Each round is its own logged attempt: `kind` stays the quiz kind (`mock`, `game`, `retest`), and the file also has `attempt_kind` (`first` for round 1, `retry` after) and `round` (1, 2, 3, ...). The score of a retry round counts only that round's questions. Older score files have neither field. `validate.py` rule R14 (`tools/sh_rounds.py`) checks these fields; `tools/test_retry_loop.py` is the headless test (CI).

When the child finishes a quiz, the page calls `SHLog.record`. The logger writes one file to the private repo `matrixmuskan/study-hub-scores`:

`G3/<Subject>/<Lesson>/<YYYY-MM-DD>T<HHMMSS>-<kind>-<rand4>.json`

The generator puts the token in the page from `STUDY_HUB_SCORES_TOKEN`. It never prints the token. If the variable is empty and the page has a quiz, the build stops. The full logger rules are in `/workspace/study-hub-scores-kit/README.md`.

## 6. Publish a page: the steps

1. Close the loop first (section 11): ingest the new school receipts, update the error log in study-hub-scores, and decide which rows the page re-tests.
2. Write the content file in your own workspace, for example `/workspace/ss/pages/Ch3-Maps.json`. Add the `provenance` block, and `src` and `retests` on each question (section 11).
3. Go to the hub repo: `cd /workspace/study-hub`.
4. Get the latest version: `git pull --rebase`.
5. Make the page: `python3 tools/sh_page.py /workspace/ss/pages/Ch3-Maps.json`. The script stops if a provenance rule fails. It writes `G3/SS/Ch3-Maps/_provenance.json` to study-hub-scores and prints the counts.
6. Make sure that the script wrote the page to `/workspace/study-hub-src/G3/SS/Ch3-Maps/index.html`.
7. Make sure that the script added or changed the entry in `manifest.json` (with `provenance_sha256` and the counts).
8. Optional: make a preview with `python3 tools/sh_page.py <file> --out /tmp/preview.html`. Open it in a browser. Delete it after you look at it.
9. Publish: `tools/publish.sh "SS: add Chapter 3 Maps"`. The script builds the hub pages, runs the checks (also the learning-loop rules B1 to B6), encrypts the changed pages, runs the validator, and commits.
10. Read the output. Make sure that it shows `validation passed`. The commit message then has the trailer `Validated: sh-2`. If the validation fails, the script makes no commit.
11. Push: `git push origin main`.
12. Send Basy the changed paths and the commit id.

The manifest entry looks like this. The generator writes it for you:

```json
{"grade": "G3", "subject": "SS", "title": "Chapter 3: Maps", "path": "G3/SS/Ch3-Maps/",
 "test_date": "2026-11-12", "added_by": "Sissy", "template": "sh-2",
 "provenance_sha256": "<64 hex>", "n_sources": 3, "n_inferred": 1, "n_questions": 12, "n_retests": 4,
 "built_at": "2026-11-12T16:05:00-08:00"}
```

## 7. Older pages that you made by hand

1. You can keep a page that you built before sh-2.
2. The publish script adds the sh-2 look and the top bar to it. The content and the scripts do not change.
3. For a new page, use the generator.
4. If you change an older page, copy it to the mirror and run `tools/publish.sh`. Do not add a second header or a second tab bar.

## 8. Encryption

1. `tools/publish.sh` reads the password from `STATICRYPT_PASSWORD` or from `~/.study-hub.env`. That file is outside the repo. It also needs `STUDY_HUB_KID_FIRST_NAME` (the child's first name, for the hub title and the private-word scrub) from the same file, and stops if it is missing. Never write the name in a tracked file (README, tools, docs, commit text): `validate.py` R12 fails on it in CI (salted hash) and on the box. Write "the child".
2. The script uses StatiCrypt 3.5.4, the salt in `.staticrypt.json`, and the login page `tools/password_template.html`.
3. The script makes the plaintext stage folder private and deletes it at the end.
4. To encrypt all pages again (for example after a design change), run `FORCE=1 tools/publish.sh "<message>"`.

## 8.1 One clone, one session at a time (publish lock)

All bots build into one shared mirror (`/workspace/study-hub-src`) and publish from one clone (`/workspace/study-hub`). Two sessions at the same time break each other: a page that one bot has built but not published fails the other bot's B1 check.

1. Use only `/workspace/study-hub` to build and publish. Never make a second clone. A clone or worktree that points at a mirror that another clone owns (`<mirror>/_state/repo`) is refused with `WRONG CLONE`.
2. Run the whole window, from the build to the push, as one locked session:
   `SH_BOT=<your name> tools/sh_lock.sh bash -c 'python3 tools/sh_page.py <page.json> && tools/publish.sh "<message>" && git push origin main'`
   For an attach, use `python3 tools/sh_provenance.py attach <fragment.json>` instead of `sh_page.py`.
3. `sh_page.py` (except `--out` previews), `sh_provenance.py attach` and `publish.sh` take the same lock (an exclusive `flock` on `<mirror>/.publish.lock`) when they run on their own. A second bot waits up to 15 minutes (`SH_LOCK_WAIT`), then stops with `LOCKED:` and the holder's name, command and start time. Wait and run your session again. Never delete the lock file. Inside a session, `SH_LOCK_HELD` must be this mirror's lock file and the lock must be held by the session that runs your command (`SH_LOCK_PID` is an ancestor process that really has the lock file open; the text in the lock file is only for people); a copied or made-up `SH_LOCK_HELD` is refused with `LOCK NOT HELD`, and a clone that does not own the mirror gets `WRONG CLONE` inside a session too. The lock stops accidents between cooperating bots; it is not a security boundary. If the clone named in `<mirror>/_state/repo` no longer exists, the next session reclaims the mirror and logs it in `<mirror>/_state/lock.log`.
4. If the push is rejected, stay in the session: run `git fetch origin` and `git rebase origin/main` (never `git pull --rebase` from an old clone after a history rewrite), then push again.
5. Branch work (tools, docs) goes in a worktree (`git worktree add /workspace/study-hub-wt/<name> -b <branch> origin/main`). A worktree does not use the shared mirror. Merges on main happen in `/workspace/study-hub` only while it is clean, inside a locked session.

## 9. Pre-push checklist

Do these checks before each push:

1. Run `python3 tools/validate.py`. Make sure that it shows `validation passed`.
2. Run `git show --stat HEAD`. Make sure that the commit holds only your page, `manifest.json`, and the hub pages.
3. Make sure that the page folder holds only `index.html`.
4. Look at each embedded image and video. Make sure that it shows no names, school logos, signs, or documents.
5. Make sure that the text has no school name, teacher names, address, birth date, or last name.
6. Make sure that the text has no em dashes.
7. Make sure that no token and no password is in any file that you changed.
8. Open the page after the push. Make sure that the password page opens and the content opens after the password.
9. Finish one quiz. Make sure that a new file comes into `study-hub-scores` (Basy can check this).

## 10. What the validator checks

`tools/validate.py` runs before each commit (from `publish.sh`) and in GitHub Actions on each push and pull request. It fails when one of these is true:

1. A page is not StatiCrypt output, or it uses the old login page.
2. A page is in the wrong folder, or it uses an unknown subject code.
3. A content page has no manifest entry, or a manifest entry has no page.
4. A page was not built from the shared template.
5. A file holds a GitHub token or the site password.
6. A plaintext file holds an em dash, or the salt changed, or `.nojekyll` is missing.
7. A file holds a private word from `STUDY_HUB_BLOCKLIST`, as plain text or hidden as base64 (at any offset) or hex. This check runs only on the box, because the list is not in the repo.
8. A page folder holds a file that is not `index.html`.
9. A page uses purple or violet, a gradient with more than one color, or a color outside the palette (white, grays, the one accent `#0066cc`, and the green, red, and amber status colors). Older pages get the palette applied for them at publish time. A new page from `sh_page.py` must pass as written.
10. A link, an anchor (`#id`), an image, a video, a poster, or a captions file does not work. Every `data:` URI must decode and have the right MIME type. Every video must have H.264 (or VP9 or AV1) video and AAC (or Opus) audio. Every manifest page must have a link on its subject hub page.
11. A page that logs scores does not have the privacy rules (privacy v4). The logger sends the score and, for each missed item: `n`, a stable item id `id` (`q<quiz>-<n>` from `sh_page.py`, or `<kind>-<n>` for older pages), the `picked` option letter, a `value` (only a typed number, or a wrong answer that the page lists in `traps`), a `trap` key (only for a wrong pick, or a typed answer that the page lists in `traps`; a blank item or an unlisted typed answer gets no trap key), and the booleans `blank` (from the page: only an empty answer) and `typed`. It never sends question text, option text, or a typed word. One exception (decided by Gilfoy, 2026-11-03): `assets/js/shlog.js` stays the logger of every other page, and a content page of subject `SpellingBee` gets it with the small additions in `tools/sh_lib.py` (`SPELL_PATCHES`, `logger_src`). Such a page, when it calls `SHLog.allow({spelling:true})`, sends, for each missed item, `typed` as the typed answer (trimmed, lowercase, letters a-z only, max 40) instead of the boolean, and a `trap` key only from the fixed spelling list (`double_letter`, `silent_letter`, `vowel_swap`, `ending`, `homophone`, `other`), set by the page's own rule-based classifier. Before the record is queued, the page drops `typed` (sends `""` and no trap) when it is not a real try at the target word: its edit distance to the target is more than max(2, floor(target length / 4)), or it is more than 2 letters longer than the target (`assets/js/spellguard.js`, inlined by the SpellingBee build; regression test `tools/test_spellguard.js`: a 4,000-pair attack set of made-up terms glued onto or into everyday words leaks at most 14, and every 1- and 2-edit misspelling is kept). The first wrong letter position (`value`) is kept. The page holds no hashes and no word lists for this. Every other subject sends what is listed above, even if it asks for this. `tools/validate.py` rule R13 (`tools/sh_typed.py`) fails a publish when a page of any other subject turns the exception on, puts any non-boolean (any string, even `""`) in `typed`, uses a spelling trap key, or has a logger copy that would send either. Other pages send `typed` as a boolean, so R13 keys on its value, not on the field. In CI it checks that the SpellingBee logger keeps the subject gate and that every other page's logger is `assets/js/shlog.js` unchanged (`tools/test_typed_text.py`). Ids and trap keys must be known: the page lists them (`SHLog.allow`, called by `sh.js` from `sh-data`), or the logger makes them from the quiz kind and `n`. `details` keep only a fixed list of keys (numbers, booleans, `mode`, known `section` ids, `rubric`, `partScores`). Each file also has `build`, the page's build id (`<meta name="sh-build">`, written at publish time; `sh_page.py` stores the same id as `build_id` in the provenance record). Each file is committed as Study Hub Bot. No page holds a private-word list. `tools/sh_stage.py` brings older logger copies up to v4 at publish time and adds small adapters for the older WW Lesson 8 and SS pages (they then send `n` and the option index). The only reference logger is `assets/js/shlog.js`.

`validate.py --src <dir>` runs only on staged output (a folder made by `tools/sh_stage.py`, as `publish.sh` does). It refuses the raw mirror with a clear message, because older pages in the mirror get their skin and logger patch only at stage time. To check by hand: `python3 tools/sh_stage.py <mirror> <tmpdir> && python3 tools/validate.py --src <tmpdir>`, then delete `<tmpdir>`.

To test the logger privacy in pages: `node tools/test_redact.js <decrypted or staged pages>`. To see the real pages log the trap and the value: `python3 tools/test_logger_pages.py` on the box (it plays a Noetic, a WW and an SS page headless, with nothing sent). It records an attempt full of free text and private words (from `STUDY_HUB_BLOCKLIST` in the env) and checks that only ids, letters, numbers and booleans leave the page, as Study Hub Bot. It prints counts only.

R14 (`tools/sh_rounds.py`): the retry-loop fields. `attempt_kind` is `first` or `retry`, `round` is an int of 1 or more (`first` with round 1, `retry` with round 2 or more), and they come together or not at all. Older score files without them pass. In CI the logger (`assets/js/shlog.js`, run under node) must send them for good input and drop bad input; with `--src` the same runs on each staged page's logger copy; `validate.py --attempts <files or folders>` checks score files.

Provenance (section 11):

- P1. A page that is not in `legacy_provenance` (in `tools/sh_config.json`) has `provenance_sha256`, `n_sources` 1 or more, and `n_questions` 1 or more in `manifest.json`. The `legacy_provenance` list can only get shorter. The validator prints a warning for each legacy page.
- P2. `n_inferred` is not more than 20% of `n_questions`.
- B7. With `--src`: a new page with a quiz has the score logger. A page that keeps results only in `localStorage` fails. For a legacy page, this is a warning.

`publish.sh` runs checks 9 and 10 on the plaintext before it encrypts anything. Then it opens every changed page in headless Chrome (`tools/sh_browsercheck.py`, which tries Playwright's Chromium first, then `/usr/bin/google-chrome`; on the box, no browser means no commit): it opens each tab, and it makes sure that every link works, every image loads, every video plays (readyState 1 or more), and no script error occurs. If a check fails, the script encrypts nothing and commits nothing.

After each push to `main` and every day, the `live-check` workflow crawls the live site (`tools/sh_livecheck.py`). The `validate` workflow also runs the end-to-end publish test (`tools/test_publish.sh`) and makes sure that every `Validated: sh-2` trailer is true.

## 11. Provenance and the learning loop

Every new page must show where each question comes from, and that it uses the child's real results. The rules apply to every page that is not in `legacy_provenance` in `tools/sh_config.json`. The pages that existed on Nov 1, 2026 are in that list. When you rebuild one of them with a provenance block, remove it from the list.

### 11.1 The format

Add a `provenance` block to the content file. In a Markdown content file, put the same JSON in a fenced block with the name `provenance`.

```json
"provenance": {
  "sources": [
    {"id": "file:/workspace/ww/lesson10/words.csv", "kind": "word_list", "sha256": "<sha256sum of the file>"},
    {"id": "file:/workspace/ww/book4/scan.pdf", "kind": "book_page", "sha256": "<sha256sum of the file>", "what": "pp. 112-114"},
    {"id": "gmail:1a164970d5ea012b", "kind": "form_receipt", "what": "WW Lesson 8 school test"}
  ],
  "results_ingested": ["gmail:1a164970d5ea012b", "gmail:1a1409dea6cffcef"],
  "weak_spots_from": ["G3/WW/Lesson9/2026-11-03T171500-mock-ab12.json"],
  "patterns_from": ["gmail:1a164970d5ea012b", "gmail:1a1409dea6cffcef"]
}
```

- `sources`: 1 or more. `id` starts with `file:`, `gmail:`, `paper:`, `url:`, `sheet:`, `handoff:`, or `school-app:`. `kind` is one of `form_receipt`, `score_released`, `word_list`, `book_page`, `study_guide`, `past_paper`, `past_form`, `teacher_notice`, `handoff`, `web`, `other`. A `file:` source must have its `sha256`. A `gmail:` source must have a receipt in study-hub-scores (11.3).
- A message from the school's parent app is `school-app:<message id>` (the number at the end of its link), with kind `teacher_notice` or `score_released`. Never use the app's link as a `url:` source and never put the app's name in an id, a `title`, or a question `src`: the name is a private word (`STUDY_HUB_BLOCKLIST`). The record lives in the private study-hub-scores repo and only its hash is public, but a source id is copied into the build history and into error-log `source` fields, so it must be neutral everywhere. On the box, `sh_page.py` and `sh_provenance.py attach` refuse a source id, title or `src` that names a blocklist word (the word is not printed).
- `results_ingested`: every school receipt and "Score released" mail for the subject that is older than the build, as `gmail:<id>`.
- `weak_spots_from`: score files from study-hub-scores that you used. Every score file of the subject that is older than the build must be here, or in an error-log note `attempt=<path>`.
- `patterns_from` (school subjects, when the page has a `mock`): past school tests of the same teacher and subject, as `gmail:<id>` receipts that are ingested (11.3). The mock must copy their format (rule F1, 11.5).
- `sh_page.py` adds `error_log` and `error_log_sha256` for you.

Each quiz question gets two more fields:

- `src`: one source `id` from the list, plus a locator after `#`. Examples: `"file:/workspace/ww/lesson10/words.csv#row=7"`, `"paper:2024S#Q13"`, `"gmail:1a11d4eee3cef24c#Q11"`. If a question has no source, use `"inferred": true` instead. Not more than 20% of the questions can be inferred.
- `retests`: the error-log row ids that this question re-tests, for example `["L8-quarry-1"]`. Use `[]` or leave it out when there are none.

A short worked example (one quiz, two questions):

```json
{"type": "quiz", "kind": "mock", "questions": [
  {"q": "Stone is cut from a", "options": ["quarry", "crop", "harbor"], "answer": 0, "word": "quarry",
   "src": "file:/workspace/ww/lesson8/words.csv#row=11", "retests": ["L8-quarry-1"]},
  {"q": "A shallow talk is", "options": ["not very serious", "very long", "about movies"], "answer": 0,
   "src": "gmail:1a1409dea6cffcef#Q11", "retests": ["L7-shallow-1"]}
]}
```

`sh_page.py` writes the full record to `study-hub-scores/G3/<Subject>/<Lesson>/_provenance.json` (private). The record is a snapshot taken at build time: `open_rows`, `error_log_sha256` and `built_at` describe the error log at that moment, so they differ from the log at HEAD after rows are added, closed or resolved. That is expected; do not rebuild a page only to refresh them. The public `manifest.json` gets only `provenance_sha256`, `n_sources`, `n_inferred`, `n_questions`, `n_retests`, and `built_at`. Source paths and question text never go into the public repo.

### 11.2 The error log

There is one error log per subject: `study-hub-scores/G3/<Subject>/_error_log.csv` (private). All coaches and Basy use this file. The columns are:

`id,date,unit,topic,skill,question,kid_answer,correct_answer,error_type,round,resolved,correct_count,last_correct_dates,source,notes`

A subject can add more columns after these (for example `sense` or `paper`). Rules:

- `id` is stable. Never change or reuse it. Examples: `L8-quarry-1` (WW), `SS-2026-09-02-1a2b3c` (made by the import when a row had no id).
- `resolved` is `no`, `yes`, `void`, or `closed`. Any other value fails the build.
  - `closed` means: the school test already happened, so the row is pattern input only, with no re-practice (Muskan's rule: when the test happens, it is done; the goal of the next test is the pattern). It is not `yes`: B6 does not apply to it, and it never needs correct answers.
  - Each subject has a mode (`subject_modes` in `tools/sh_config.json`). School: SS, WW, LA, Math, Sci, Grammar. Contest: Noetic, Kangaroo, MOEMS, SpellingBee.
  - When a real school test happens, set `closed` on its rows (`python3 tools/migrate_error_logs.py --close-school` does this for rows with `round=school`). Rows from practice (mock, game, retest) stay `no`.
- The open rows that B5 counts:
  - School subject: only `no` rows dated after the last real school test of the subject (the current prep window). The last test is the newest ingested receipt of the subject, or the newest `round=school` row. Older `no` rows are ignored (`plan` lists them so you can close them).
  - Contest subject: every `no` row (cumulative).
- Each new page re-tests the open rows in a rotation (rule B5), so a page never has to re-test all of them:
  - (a) The page re-tests at least min(15, open rows), chosen oldest-first: first the open rows that were re-tested least recently (never re-tested comes first), then by row `date`, then by `id`.
  - (b) Every open row is re-tested at least once in any 3 consecutive builds of the subject. A row that was open in the last 2 builds and was re-tested in neither must be re-tested in this build.
  - (c) A row that was missed again since the last build must be re-tested in this build. "Missed again" means a later attempt has the row's question in `missed`, or the row has an `attempt=` note with a later attempt.
  - Every id in `retests` must be a real row.
  - To see what to re-test, run `python3 tools/sh_provenance.py plan G3/<Subject>`. It prints the ids to put in `retests`, then a `patterns` section: the closed rows with their trap types (`error_type`) and question styles (`skill`). Use them to shape the mock (rule F1), not as re-practice. The build history is in `study-hub-scores/G3/<Subject>/_builds/` (`sh_page.py` writes one copy per build, with the open rows at that time).
- A row can be `yes` only after 2 correct answers on the same fact, on 2 different days (Pacific time). Put each one in `notes` as `correct=<attempt path>`, set `correct_count` to 2 or more, and put both days in `last_correct_dates` (for example `2026-11-03;2026-11-05`). The page of each attempt must have a question with this row id in `retests`, and the attempt must not list that question in `missed` (rule B6).
- Put each score file that you read in `notes` as `attempt=<path>`.

The old box logs (`/workspace/<coach>/error_log.csv`) were imported by `tools/migrate_error_logs.py`. They are kept, but study-hub-scores is now the log that the rules read.

### 11.3 School receipts

1. Fetch each Google Forms receipt and "Score released" mail with your own personal-Gmail connector (`read_email` with `messageFormat` `FULL_CONTENT`). Save the JSON result to a file in your workspace.
2. Run `python3 tools/ingest_receipts.py <file or folder>` on the box. It reads the HTML body (the plain-text body does not show the picked answers), drops name and email questions, replaces private words with `[name]`, and writes `study-hub-scores/G3/_receipts/<gmail-id>.json`. It never calls Gmail, and it does not run in CI.
3. Add a row to the error log for each miss, and add the receipt to `results_ingested` of the next page.

### 11.4 Where each rule runs

| Rule | What | Where |
|---|---|---|
| B8 | every question id in a page's provenance record is an id that the page's logger sends, so logged misses join to their sources | `validate.py --src` (box, in `publish.sh`) |
| P1, P2 | hash and counts in `manifest.json`; not more than 20% inferred; `legacy_provenance` only gets shorter | `validate.py` (CI and box), `sh_page.py` |
| B1 | `_provenance.json` exists and its hash is `provenance_sha256` | `publish.sh` (`tools/sh_provenance.py check`) |
| B2 | every question has `src` or `inferred`; `file:` sources exist with the same sha256; `gmail:` ids have a receipt | `sh_page.py`, `publish.sh` |
| B3 | every older score file of the subject is in `weak_spots_from` or an `attempt=` note | `publish.sh` |
| B4 | every older receipt of the subject is in `results_ingested` | `publish.sh` |
| B5 | re-test rotation over the open rows B5 counts (school: `no` rows after the last real school test; contest: every `no` row): at least min(15, open rows) oldest-first; every open row once in any 3 consecutive builds; a row missed again since the last build now. `resolved` is one of `no`, `yes`, `void`, `closed`; `closed` rows never count | `publish.sh` (`plan` shows the ids) |
| B6 | `resolved=yes` only with 2 correct answers on 2 PT days | `publish.sh` |
| B7 | a page with a quiz logs to study-hub-scores | `sh_page.py`, `validate.py --src` |
| F1 | a school-subject mock cites `patterns_from` (required) and matches their question count, question types, option count and length (warning) | `sh_page.py` (required, prints the comparison), `publish.sh` (warning) |
| F2 | every real test from 2026-11-05 on has a full mock that logs (static); the coach logs a full mock at least 24 hours before the test (logs) | `validate.py --src` (box, in `publish.sh`: fail or warning, 11.7); `tools/check_f2.py` (box, Basy) |

`publish.sh` checks B1 to B6 for each changed page that is not a legacy page. It needs `STUDY_HUB_SCORES_TOKEN`. If a rule fails, it encrypts nothing and commits nothing. Tests: `tools/test_provenance.py` (CI), `tools/test_f2.py` (CI, rule F2), `tools/test_publish.sh` cases 5 and 6 (CI), `tools/test_provenance_box.py` (box, fixture subject).

### 11.5 School mocks match the real test (rule F1)

For school subjects (`subject_modes` in `tools/sh_config.json`: SS, WW, LA, Math, Sci, Grammar are `school`), the goal of a training page is a mock paper with the same difficulty and format as the real school test. Contest subjects (Noetic, Kangaroo, MOEMS) use past papers instead.

The pattern input is the past school receipts in `patterns_from` and the subject's `closed` rows (11.2): their trap types (`error_type`) and question styles (`skill`). `sh_page.py` and `plan` print them. Build the mock to the same traps and styles, with new items, not the old questions again.

1. A page with a `mock` quiz must have `patterns_from`: 1 or more past school receipts of the same teacher and subject. `sh_page.py` stops without it. Each id must be an ingested receipt of the same subject (rule B2).
2. `sh_page.py` prints a comparison of the mock with the mean of those receipts:

```
format vs 2 school test(s):                        mock  school
  questions                  30      31
  multiple choice          100%    100%
  options per question      4.0     4.0
  words per question         11      10   (difficulty proxy)
```

3. The mock must match within these limits (`F1_TOL` in `tools/sh_provenance.py`): question count within 20% or 3 questions (the larger), share of multiple-choice questions within 15 points, options per question within 0.5, words per question within 40%.
4. Out of range gives a warning from `sh_page.py` and from `publish.sh` (`WARNING: F1 ...`). It does not stop the build, because a coach can have a reason (for example a short practice mock). Write the reason in the coach SOURCE file. Basy reads the warnings.

### 11.6 Pages from before the rules (attach)

A page in `legacy_provenance` that was not built with `sh_page.py` can get a record without a rebuild. Write a fragment `{"page", "provenance": {"sources", "results_ingested", "weak_spots_from"}, "questions": [{"id", "q", "src" or "inferred": true, "retests"}], "prompts"}` (for example `/workspace/ss/provenance/Final1-Ch1-2-8.provenance.json`), then run `python3 tools/sh_provenance.py attach <fragment.json>` on the box. It gives each question the id that the page's logger sends (`q<quiz>-<n>`, as `sh_page.py` numbers them; the question is matched to the page's `sh-data` by its text, so the fragment's own ids such as `practice-1` or `mock-1` are replaced, and `quiz` is the page's quiz number; a page with no `sh-data` in the mirror fails the attach), checks the fragment (B1, B2, P2, real `retests` ids, B6), writes the record with `"attached": true` to study-hub-scores, adds the hash and counts to the manifest entry, and takes the page out of `legacy_provenance`. The next `tools/publish.sh` run commits that `legacy_provenance` change together with `manifest.json`, so the shared tree is clean after the publish (no extra PR is needed). `publish.sh` checks first (`sh_provenance.py config-diff`): it stages `tools/sh_config.json` only when the one change since HEAD is pages taken out of `legacy_provenance` and each of them has a `provenance_sha256` in the manifest. Any other uncommitted change to `tools/sh_config.json` stops the publish before anything is encrypted; that change goes through a PR. B3, B4 and the B5 rotation do not apply to an attached record, because they are rules for new builds. `attach` refuses a page that is not in `legacy_provenance`, and the list can only get shorter.

### 11.7 A full mock is logged 24 hours before each real test (rule F2)

Decided by Gilfoy, effective Nov 3, 2026. Gilfoy's words: before each real school test or contest, the coach must log at least one full mock attempt in study-hub-scores (kind mock, with the predicted score) at least 24 hours before the test. If there is no mock log, that test is a loop failure for that coach, and Basy escalates it to Gilfoy.

- Owner: the coach of the subject (the bot in `added_by`). Basy checks and escalates. Gilfoy decides.
- A real test is one grade, subject and `test_date` in `manifest.json`. All pages with the same grade, subject and `test_date` share the test, so one full mock log on any of them covers the test.
- Start date: F2 applies to real tests on or after Thu 2026-11-05 (the WW Lesson 9 test is the first). Tests on or before 2026-11-04 are exempt. There are no back-dated failures. The cutoff is `F2_CUTOFF` in `tools/sh_f2.py`.
- What counts: an attempt file in `study-hub-scores/G3/<Subject>/<Lesson>/` for a lesson of the test, with kind `mock`, the first round of the full mock (not a `retry` round), and a score out of the full mock total (the score is the predicted score). The full mock has 10 or more questions (`F2_MIN_QUESTIONS`). A mock that is shorter only because the real test is shorter needs `"full": true` on the quiz block; write the reason in the coach source file. A mini check (for example a 6-question mastery quiz) does not count.
- When: the attempt is logged at least 24 hours before the test starts, in America/Los_Angeles time. The manifest has only the date, so the test starts at 08:00 Pacific on `test_date` (`F2_TEST_TIME`). Example: for a test on Thu 2026-11-05, the mock must be logged by Wed 2026-11-04 08:00 Pacific. The time comes from the file's `clientTime` (with its offset), or from the file name stamp read as Pacific time.
- Failure: no full mock log before the test, after the deadline has passed, is a loop failure for that coach. A full mock logged less than 24 hours before the test is LATE. Basy escalates both to Gilfoy.

The checks:

1. Static (`validate.py --src`, so on the box and in every `publish.sh` run; the repo pages are encrypted, so CI cannot read them). For each manifest entry with a `test_date` on or after 2026-11-05, the page needs a full mock that logs: a quiz with `kind` `mock`, `mode` `test`, 10 or more questions (or `"full": true`), `log` on in `sh-data`, and the score logger. Then a predicted score can be logged.
   - Fail (`F2:`): no page of the test has a full mock that logs. The publish stops.
   - Warning: this page has no full mock, but another page of the same test has one (for example the Noetic chapter quizzes, where the warm-up mock page covers the 2026-11-19 contest). Also a warning: every page of the test is an older page with no `sh-data`, so its quizzes cannot be read.
   - This keeps every page that is live on Nov 3, 2026 passing: WW Lesson 9 (2026-11-05) has a 32-question mock, and the Noetic 2026-11-19 pages are covered by the warm-up mock page.
2. Logs (`tools/check_f2.py`, box only, never in public CI because it needs `STUDY_HUB_SCORES_TOKEN`). Basy runs it every day and before each test:

```sh
python3 tools/check_f2.py            # report only
python3 tools/check_f2.py --strict   # exit 1 when a test is MISSING or LATE
```

   It prints one line per test: `PASS` (a full mock was logged 24 hours or more before), `LATE` (logged, but less than 24 hours before), `MISSING` (no full mock before the test and the deadline has passed), or `PENDING` (the deadline is still ahead and no full mock is logged yet). It prints counts and attempt paths only, never scores or file contents. It exits 2 with `F2 CHECK DID NOT RUN` when there is no token or no network. Options: `--now <ISO time>`, `--test-time HH:MM`, `--manifest <path>`. Basy sends each MISSING or LATE test to Gilfoy with the test, the coach and the paths.
3. Tests: `tools/test_f2.py` (CI) uses made-up pages and a fixture score folder (`STUDY_HUB_SCORES_DIR`).

