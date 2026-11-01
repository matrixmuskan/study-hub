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
2. Use one of these subject codes: `SS`, `WW`, `Noetic`, `Kangaroo`, `MOEMS`, `Math`, `Sci`, `LA`, `Grammar`.
3. To add a subject code, add it to `tools/sh_config.json`. Give it a name, a two-letter mark, and one accent color. Tell Basy.
4. Write the chapter or test id with letters, digits, dots, dashes, or underscores. Do not use spaces. Examples: `Lesson10`, `Ch3-Maps`, `Final2-Ch3-4`.
5. Do not put other files in the page folder. Keep sources, notes, images, and PDFs in your own workspace.

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
- `templates/page.example.md` (text and quizzes)

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
| `image` | `src`, `alt`, `caption` | An image. `src` is a path next to the content file. The generator embeds it. `alt` is necessary. |
| `quiz` | `kind`, `title`, `intro`, `mode`, `questions` | A quiz. See section 5. |
| `html` | `html` | Your own HTML. Use it only when no other block type works. Use the `sh-` classes from `assets/css/sh.css`. |

### Markdown format

1. Start the file with front matter between two `---` lines. Write one field on each line, for example `title: Lesson 10 words`.
2. Start each section with `# <Label>`, for example `# Learn`.
3. Write the text in Markdown.
4. Put a quiz in a fenced block that starts with ```` ```quiz ````. Write the quiz as JSON.

## 5. Quizzes and score logging

1. Set `kind` to `game`, `mock`, or `retest`. The logger uses `kind` in the file name.
2. A `game` gives the answer after each question. A `mock` or `retest` gives the score after "Mark my test". Use `mode` (`practice` or `test`) to change this.
3. Write each question with `q`, then one of these:
   - `options` (a list) and `answer` (the index of the right option, starting at 0).
   - `answer_text` (a string or a list of strings that are correct). Add `"numeric": true` for a number keyboard.
4. Add `explain` to show a short reason after the answer.
5. Add `word`, `sense`, `topic`, or `trap` when they help. The logger sends them for missed questions.
6. Do not put names or private information in questions.

When the child finishes a quiz, the page calls `SHLog.record`. The logger writes one file to the private repo `matrixmuskan/study-hub-scores`:

`G3/<Subject>/<Lesson>/<YYYY-MM-DD>T<HHMMSS>-<kind>-<rand4>.json`

The generator puts the token in the page from `STUDY_HUB_SCORES_TOKEN`. It never prints the token. If the variable is empty and the page has a quiz, the build stops. The full logger rules are in `/workspace/study-hub-scores-kit/README.md`.

## 6. Publish a page: the steps

1. Write the content file in your own workspace, for example `/workspace/ss/pages/Ch3-Maps.json`.
2. Go to the hub repo: `cd /workspace/study-hub`.
3. Get the latest version: `git pull --rebase`.
4. Make the page: `python3 tools/sh_page.py /workspace/ss/pages/Ch3-Maps.json`.
5. Make sure that the script wrote the page to `/workspace/study-hub-src/G3/SS/Ch3-Maps/index.html`.
6. Make sure that the script added or changed the entry in `manifest.json`.
7. Optional: make a preview with `python3 tools/sh_page.py <file> --out /tmp/preview.html`. Open it in a browser. Delete it after you look at it.
8. Publish: `tools/publish.sh "SS: add Chapter 3 Maps"`. The script builds the hub pages, encrypts the changed pages, runs the validator, and commits.
9. Read the output. Make sure that it shows `validation passed`.
10. Push: `git push origin main`.
11. Send Basy the changed paths and the commit id.

The manifest entry looks like this. The generator writes it for you:

```json
{"grade": "G3", "subject": "SS", "title": "Chapter 3: Maps", "path": "G3/SS/Ch3-Maps/",
 "test_date": "2026-11-12", "added_by": "Sissy", "template": "sh-2"}
```

## 7. Older pages that you made by hand

1. You can keep a page that you built before sh-2.
2. The publish script adds the sh-2 look and the top bar to it. The content and the scripts do not change.
3. For a new page, use the generator.
4. If you change an older page, copy it to the mirror and run `tools/publish.sh`. Do not add a second header or a second tab bar.

## 8. Encryption

1. `tools/publish.sh` reads the password from `STATICRYPT_PASSWORD` or from `~/.study-hub.env`. That file is outside the repo.
2. The script uses StatiCrypt 3.5.4, the salt in `.staticrypt.json`, and the login page `tools/password_template.html`.
3. The script makes the plaintext stage folder private and deletes it at the end.
4. To encrypt all pages again (for example after a design change), run `FORCE=1 tools/publish.sh "<message>"`.

## 9. Pre-push checklist

Do these checks before each push:

1. Run `python3 tools/validate.py`. Make sure that it shows `validation passed`.
2. Run `git show --stat HEAD`. Make sure that the commit holds only your page, `manifest.json`, and the hub pages.
3. Make sure that the page folder holds only `index.html`.
4. Look at each embedded image. Make sure that it shows no names, school logos, signs, or documents.
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
7. A file holds a private word from `STUDY_HUB_BLOCKLIST`. This check runs only on the box, because the list is not in the repo.
8. A page folder holds a file that is not `index.html`.
