---
inclusion: manual
description: "Build and package the SCORM zip: single-page SCO architecture, the Eleventy build, imsmanifest.xml, the pipwerks binding fix, COURSE_ROOT multi-course resolution, and the Rustici completion-tracking rationale. Read when diagnosing a build or packaging issue (pipeline steps 5-6)."
---

# SCORM Authoring

Covers building the authored SCORM package that uploads to the LMS: lesson markdown → static HTML via Eleventy → wrapped with a SCORM manifest + API library → zipped. Read at pipeline steps 5-6.

> **Architecture note — single-page SCO.** An earlier version produced a multi-page SCO (one HTML file per lesson under `pages/`). It caused Rustici-backed LMS tenants to mark every course complete on the first Save-and-Exit. The root cause and fix are in [Why single-page: the Rustici story](#why-single-page-the-rustici-story). If you find an old course repo with `pages/` in its build output, migrate it to single-page before shipping — there is no patch that makes multi-page work on affected tenants.

## What gets produced

One deliverable: a SCORM 1.2 `.zip` at `scorm/dist/<course-short-name>.zip`. Inside, at the zip root:

```
imsmanifest.xml              ← manifest, lists only index.html + assets
index.html                   ← ONE HTML file: home view + every lesson body
assets/
  css/course.css
  js/scorm_api_wrapper.js    ← pipwerks wrapper (WITH binding fix, see below)
  js/course.js               ← SPA runtime: routing, commits, knowledge checks
  images/<module-id>/...     ← images referenced by lesson bodies
```

No `pages/` subdirectory, no per-lesson HTML files.

## Single-page, single-SCO architecture

- **One `<item>` in the manifest** — the LMS tracks the course as one unit.
- **One HTML file** — `index.html` holds the home view, the lesson reading view, and every lesson body as an inert `<template>`.
- **One `LMSInitialize` per session** — navigation is JS-driven (hash routing, template cloning). No page reload, no second init. Because init runs once, `pipwerks.SCORM.connection.isActive` stays true and later `scorm.set()` calls persist.
- **Completion is automatic** — set once when the learner reaches the last lesson with every page's gating satisfied (all pages visited). Every other commit re-asserts `lesson_status="incomplete"` + `cmi.core.exit="suspend"` so mid-course exits leave the SCO in progress.
- **Progress persistence** via `cmi.core.lesson_location` (current slug) and `cmi.suspend_data` (JSON array of visited slugs).

Multi-page within a single SCO breaks completion tracking on some Rustici tenants — see the rationale section.

## SCORM version: 1.2

Use SCORM 1.2: widely supported, simpler CMI surface, and 2004's sequencing is irrelevant when navigation is authored in JS. The pipwerks wrapper handles both versions, so switching later is mostly a manifest change.

**Mastery score is required.** The manifest carries `<adlcp:masteryscore>` on the `<item>` (templated from `scorm.passing_score`, default 100). Without it, Rustici's rollup-on-exit heuristic marks the SCO complete regardless of learner state. With it, Rustici requires `cmi.core.score.raw >= masteryscore` — which only the auto-completion path sets.

## Build pipeline

```
build/module-N/lesson.md, visuals/*
        │  Eleventy: renders every lesson body into ONE index.html
        ▼
scorm/build/{imsmanifest.xml, index.html, assets/}
        │  zip from INSIDE scorm/build/
        ▼
scorm/dist/<course-short-name>.zip
```

**Why Eleventy:** Node-based static output (no DB/server), markdown-first, shortcodes (`{% tip %}`, `{% knowledgeCheck %}`, `{% nextPage %}`), and filters that render each lesson body through Nunjucks + markdown-it into a single template (`renderLessonBody`). Small, stable, version-controllable. Astro/Next.js are overkill; hand-rolled templates lose the ergonomics; authoring tools lock content in proprietary formats.

## Directory layout (`scorm/src/`)

```
scorm/src/
├── .eleventy.js            ← config: collection from build/module-*/lesson.md; COURSE_ROOT switch
├── package.json            ← @11ty/eleventy, markdown-it, js-yaml (pin versions)
├── index.njk               ← the one SCO HTML: home + lesson view + all lesson <template>s
├── imsmanifest.xml.njk     ← manifest template (only index.html + assets listed)
└── assets/{css/course.css, js/scorm_api_wrapper.js, js/course.js}
scorm/build/                ← Eleventy output (gitignored)
scorm/dist/                 ← zipped SCORM (gitignored)
```

No `pages/`, no `_includes/` layouts, no per-page pagination. The course is one HTML file.

## The manifest (`imsmanifest.xml`)

SCORM 1.2 manifest, templated per course:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{{ course.short_name }}-manifest" version="1.0"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="...">
  <metadata><schema>ADL SCORM</schema><schemaversion>1.2</schemaversion></metadata>
  <organizations default="org-{{ course.short_name }}">
    <organization identifier="org-{{ course.short_name }}">
      <title>{{ course.title }}</title>
      <item identifier="item-{{ course.short_name }}" identifierref="res-{{ course.short_name }}">
        <title>{{ course.title }}</title>
        <!-- REQUIRED for Rustici compatibility; from scorm.passing_score (default 100). -->
        <adlcp:masteryscore>{{ scormConfig.passing_score or 100 }}</adlcp:masteryscore>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res-{{ course.short_name }}" type="webcontent"
              adlcp:scormtype="sco" href="index.html">
      <file href="index.html"/>
      <file href="assets/css/course.css"/>
      <file href="assets/js/scorm_api_wrapper.js"/>
      <file href="assets/js/course.js"/>
      <!-- One <file> per shipped image. .eleventy.js collects passthrough-copied
           image hrefs into `imageFiles`; IMS Content Packaging requires every
           packaged file to be enumerated, so images cannot be omitted. -->
      <file href="assets/images/module-1/slide-01.png"/>
      <!-- ...one per image... -->
    </resource>
  </resources>
</manifest>
```

**Identifier rules:** `kebab-case`, ASCII only, no spaces; unique within the manifest; stable across rebuilds (don't regenerate random UUIDs each build).

## The `index.njk` template (the whole SCO)

One HTML document with three parts:

1. **`#home-view`** — module cards, shown when the hash is empty.
2. **`#lesson-view`** (hidden on home) — sidebar + reading column (`#lesson-content`) + prev/next footer.
3. **One `<template data-lesson-template="{slug}">` per lesson**, carrying `data-module-id`, `data-prev-slug`, `data-next-slug`, and `data-is-course-end`. Body rendered via `{{ page.body | renderLessonBody(page.frontmatter, page.module_id) | safe }}`.
4. **`<script id="course-manifest" type="application/json">`** — the single source of truth for runtime navigation (`totalLessons`, per-lesson chain). `course.js` reads it once on boot instead of walking the template tree.

Design notes:
- `<template>` content is parsed but inert until cloned into the live DOM — images don't load and scripts don't fire until the learner navigates there, keeping initial paint fast.
- Image paths are rewritten by `renderLessonBody` at build time (each body knows its `module_id`), **not** by a post-render transform.

Full template lives at `scorm/src/index.njk`.

## Eleventy `renderLessonBody` filter

Inlines each lesson body into the shared `index.html`:

```js
// scorm/src/.eleventy.js
config.addFilter("renderLessonBody", function (body, frontmatter, moduleId) {
  const text = String(body || "");
  let afterShortcodes = this.env.renderString(text, { frontmatter: frontmatter || {} }); // 1. shortcodes
  let html = md.render(afterShortcodes);                                                  // 2. markdown → HTML
  if (moduleId) {                                                                          // 3. rewrite image paths
    html = html.replace(/(<img\s[^>]*src=")visuals\/([^"]+)(")/g,
      `$1assets/images/${moduleId}/$2$3`);
  }
  return html;
});
```

There is NO `rewrite-image-paths` post-render transform keyed off `outputPath` — an earlier version used one, but it breaks when every lesson body renders into the same output file.

## The pipwerks SCORM wrapper (with binding fix)

The **pipwerks SCORM API Wrapper** (single-file, MIT, SCORM 1.2 + 2004) is vendored: grab `SCORM_API_wrapper.js` from `https://github.com/pipwerks/scorm-api-wrapper`, save to `scorm/src/assets/js/scorm_api_wrapper.js`, and commit it (don't fetch at build time).

### The critical binding fix

The wrapper's top-level convenience facade aliases lose their `this` binding:

```js
// ❌ Ships broken — `this` becomes pipwerks.SCORM, which has no toBoolean():
pipwerks.SCORM.init = pipwerks.SCORM.connection.initialize;
pipwerks.SCORM.get  = pipwerks.SCORM.data.get;
pipwerks.SCORM.set  = pipwerks.SCORM.data.set;
pipwerks.SCORM.save = pipwerks.SCORM.data.save;
pipwerks.SCORM.quit = pipwerks.SCORM.connection.terminate;
```

The methods call `this.toBoolean(...)`, which only resolves when `this` is the owning sub-object (`connection`/`data`). Via the top-level alias it throws `Uncaught TypeError: this.toBoolean is not a function` on the first `LMSInitialize` — the SCO boot crashes, no `cmi.*` writes reach the LMS, and Rustici defaults to "completed" on exit.

```js
// ✅ Required fix — bind each alias to its owning sub-object:
pipwerks.SCORM.init = pipwerks.SCORM.connection.initialize.bind(pipwerks.SCORM.connection);
pipwerks.SCORM.get  = pipwerks.SCORM.data.get.bind(pipwerks.SCORM.data);
pipwerks.SCORM.set  = pipwerks.SCORM.data.set.bind(pipwerks.SCORM.data);
pipwerks.SCORM.save = pipwerks.SCORM.data.save.bind(pipwerks.SCORM.data);
pipwerks.SCORM.quit = pipwerks.SCORM.connection.terminate.bind(pipwerks.SCORM.connection);
```

Apply this to the vendored copy with a comment explaining why. Upstream may fix it eventually — verify before upgrading.

## `course.js` runtime (SPA model)

Full implementation at `scorm/src/assets/js/course.js`. Five responsibilities:

1. **Initialize SCORM once** on `DOMContentLoaded`, inside `try/catch` so a wrapper crash falls back to preview mode instead of white-screening. On success, seed `score.raw=0`, `score.min=0`, `score.max=100`, then re-assert incomplete+suspend unless the attempt is already `completed`.
2. **Hash routing** — empty hash = home, `#module-1-page-03` = that lesson. React to `popstate`/`hashchange` for browser back/forward.
3. **Lesson rendering** — clone the matching `<template>` into `#lesson-content`, update sidebar highlight and prev/next footer, scroll to top.
4. **Per-navigation commit** — on every transition set `cmi.core.lesson_location`, re-assert `lesson_status="incomplete"` + `exit="suspend"`, then `save()`. This is what keeps Rustici from rolling up to complete.
5. **Completion** — reaching the last lesson with all pages visited is the ONE path that sets `lesson_status="completed"`, clears `exit`, sets `score.raw=100`, and saves. Automatic; no manual Finish button. Never fires on a mid-course last-page load or on exit.

Commit helpers follow this contract (each `set` in its own `try/catch`, always `save()` after `set()`):

```js
function markAsSuspend() { scorm.set("cmi.core.lesson_status","incomplete"); scorm.set("cmi.core.exit","suspend"); }
function commitSuspend() { markAsSuspend(); scorm.save(); }          // every navigation
function markComplete()  { scorm.set("cmi.core.exit",""); scorm.set("cmi.core.lesson_status","completed");
                           scorm.set("cmi.core.score.raw","100"); scorm.save(); }  // auto-completion only
// teardown() on beforeunload: if not completed, markAsSuspend(); then save(); quit();
```

### Sidebar visited-state: trust the LMS

When connected, `cmi.suspend_data` is the single source of truth for visited lessons. Do **not** fall back to `localStorage` when suspend_data is empty on a live session — empty means "fresh attempt," not "check localStorage," and falling back surfaces stale markers from prior authoring sessions.

```js
function loadVisited() {
  if (connected) {
    try { const raw = scorm.get("cmi.suspend_data") || "";
          const parsed = raw ? JSON.parse(raw) : [];
          return Array.isArray(parsed) ? parsed : []; }
    catch (e) { return []; }
  }
  // Preview mode ONLY: localStorage so reloads preserve position.
  try { const raw = localStorage.getItem(VISIT_STORAGE_KEY) || ""; return raw ? (JSON.parse(raw) || []) : []; }
  catch (e) { return []; }
}
```

Same rule for `saveVisited`: when connected, write only to the LMS.

## SCORM CMI fields used

| Field | Usage |
|---|---|
| `cmi.core.lesson_location` | Current lesson slug; set on every navigation; used to resume on re-launch. |
| `cmi.core.lesson_status` | `"incomplete"` on every commit until auto-completion; `"completed"` only on auto-completion. |
| `cmi.core.exit` | `"suspend"` on every commit until auto-completion; empty string on auto-completion. |
| `cmi.core.score.raw` | Seeded `0` on init (below mastery); `100` on auto-completion. |
| `cmi.core.score.min` / `.max` | Set to `0` / `100` on init. |
| `cmi.suspend_data` | JSON array of visited lesson slugs. |
| `cmi.core.session_time` | Handled automatically by the wrapper. |

## Knowledge check widget

Authored in `lesson.md` via `{% knowledgeCheck %}` (see `lesson-authoring.md` for the full option/feedback schema). A delegated click handler in `course.js` intercepts `.kc-option` clicks, reveals feedback, locks the options, and commits the suspend state when the check is `graded: true`.

**What it tracks — and doesn't:** the shortcode commits `suspend_data` + `lesson_status=incomplete` + `exit=suspend` when a learner answers (so answered state survives sessions), but it does **not** write `cmi.interactions.*` or `cmi.core.score.raw`. The LMS sees lesson progression and completion, not per-question scores. This is intentional — completion is mastery-score-driven, which is the Rustici workaround; per-question scoring is optional UX polish, not part of the completion contract. SCORM 1.2's `cmi.interactions.*` is sparsely supported across LMSes; only wire it (a ~30-50 line addition to the handler, plus stable `data-id`/`data-letter` per option) if a platform owner actually asks for per-question data.

## Multi-course from one builder (`COURSE_ROOT`)

All courses live at `courses/<name>/` with their own `course.yaml` + `build/` tree. The builder resolves any course uniformly via the `COURSE_ROOT` env var.

```js
// top of .eleventy.js
const DEFAULT_REPO_ROOT = path.resolve(__dirname, "../..");
const REPO_ROOT = process.env.COURSE_ROOT ? path.resolve(process.env.COURSE_ROOT) : DEFAULT_REPO_ROOT;
const COURSE_YAML = path.join(REPO_ROOT, "course.yaml");
```

`scripts/build-scorm.sh <course>` always sets `COURSE_ROOT`, so every course resolves identically. When unset (running Eleventy by hand), it falls back to a `course.yaml` two levels up. **Search `.eleventy.js` for every `path.resolve(__dirname, ...)` before committing** — a second `REPO`-like constant (dev-server watch targets, etc.) often lurks and needs the same treatment; missing one silently breaks incremental reload.

**Key rule: no per-course special cases in the shared script.** All courses resolve via `$REPO_ROOT/courses/$COURSE`. If a course needs different behavior, encode it in that course's `course.yaml`, not in conditional branches.

**Regression discipline** — before claiming a builder change is a no-op for existing courses, checksum the build output before and after and diff:

```bash
scripts/build-scorm.sh <course>
( cd scorm/build && find . -type f -print0 | xargs -0 shasum ) | sort -k 2 > /tmp/baseline.txt
# ...make change, rebuild...
( cd scorm/build && find . -type f -print0 | xargs -0 shasum ) | sort -k 2 > /tmp/after.txt
diff /tmp/baseline.txt /tmp/after.txt   # expect only the files you intended to change
```

**gitignore** — use globs that cover every course, not root-anchored rules:

```gitignore
**/scorm/build/
**/scorm/dist/
courses/*/build/thumbnail.png
```

## Content-from-`course.yaml` conventions

- **Home-page description:** don't hardcode the description paragraph in `index.njk`. Put it on `course.short_description` and read it in the template (`{% if course.short_description %}...{% endif %}`), so each course owns its own copy and the template stays generic.
- **Inline markdown in shortcodes** (`{% objectives %}`, knowledge-check options/feedback): run each authored string through markdown-it's **inline** renderer (`mdInline`), not a plain HTML-escaper (`escHtml`) — authors expect `**bold**`/`*italic*` to render, not show literal asterisks. When rendered markdown must travel inside a `data-*` attribute (canonically `data-feedback`), build-time `escHtml(mdInline(...))` into the attribute, then at runtime use `innerHTML` (not `textContent`) so the `<em>`/`<strong>` render. Leave a comment noting it's safe (server-rendered from trusted `lesson.md`, not learner input) so nobody "fixes" it back to `textContent`.

## Completion strategy

Completion is **automatic and gated on progression**: marked complete only when the learner reaches the last lesson AND every page's gating is satisfied (dwell elapsed + all knowledge checks answered, so every page is visited). No manual Finish button; never fires on mid-course exit or a mid-course last-page load. This keeps the `masteryscore` contract honest — completion happens exactly when `score.raw >= masteryscore`.

Configure in `course.yaml`:

```yaml
scorm:
  min_page_dwell_seconds: 5    # per-page Next-button dwell gate (0 disables)
  passing_score: 100           # must match masteryscore in the manifest
```

`completion_strategy` may still appear in older `course.yaml` files; it is **documentary only, not read by the pipeline**. The runtime always uses the automatic gating above.

## Preview and testing (all local)

Local preview (no LMS, so `scorm.init()` returns false → preview mode; navigation/checks/auto-completion work but don't persist; visited pages go to localStorage):

```bash
cd scorm/src && COURSE_ROOT=../../courses/<name> npx @11ty/eleventy
cd ../build && python3 -m http.server 8080   # open http://localhost:8080/
```

Verify SCORM behavior without any upload:

- **Structure + manifest:** `python3 scripts/validate-scorm.py courses/<name>/scorm/dist/<name>.zip` — checks manifest placement, schema 1.2, mastery score, referenced-file presence, single-page structure.
- **Runtime contract:** the runtime tier loads the built zip in jsdom against [scorm-again](https://github.com/jcputney/scorm-again) and asserts `LMSInitialize` once per session, the incomplete+suspend baseline, auto-completion with score 100 after a full walkthrough, mid-course exits staying incomplete, and bookmark resume.

  ```bash
  npm --prefix tests/runtime install   # once
  scripts/build-scorm.sh <name>
  npm --prefix tests/runtime test
  ```

For a final end-to-end check, upload the validated zip to your own SCORM 1.2 LMS.

Many enterprise LMSes run Rustici Engine, so a package passing the validator + runtime tier behaves predictably; the main source of tenant variance is the platform's custom player wrapper.

## Packaging and upload

Build invariants enforced by `scripts/build-scorm.sh`:

- **Clean previous build** — `rm -rf scorm/build` before every build; Eleventy doesn't prune stale files, and a warm dir can carry stale `pages/*.html` into the zip.
- **Zip from INSIDE the build dir** — most LMSes require `imsmanifest.xml` at the zip root; zipping the parent produces a nested folder that gets rejected.
- Zip destination comes from `scorm.output` in `course.yaml`, resolved relative to the course root.

Then validate, and never suggest uploading a package that fails:

```bash
python3 scripts/validate-scorm.py courses/<name>/scorm/dist/<name>.zip
```

To upload: in the LMS content area create a training, choose SCORM upload, upload the zip, fill metadata from `build/course-metadata.md` (title, description, tags, language), add the thumbnail and duration, save as draft, publish when ready.

## Iterating

1. Edit `lesson.md`. 2. `scripts/build-scorm.sh <course>`. 3. **Unpublish and republish the training** — on Rustici tenants a straight replacement can reuse the old registration; unpublish/republish forces a clean test session. 4. For existing learners, whether progress resets depends on LMS policy.

Keep builds reproducible: pin the Eleventy version in `package.json`, commit the pipwerks wrapper with the binding fix, and commit `course.yaml` changes alongside lesson edits.

## Why single-page: the Rustici story

The old multi-page SCO (one HTML file per lesson under `pages/`) marked every course **"Completed" on the first Save-and-Exit**, regardless of content viewed. Decoded session trace:

1. Launch → our SCO's `scorm.init()` succeeds (`isActive=true`), commits `incomplete` + `exit=suspend`. Good.
2. Click Next → browser navigates to the next page HTML → old page's `beforeunload` fires `scorm.quit()`, but Rustici's session is still alive.
3. New page's boot calls `scorm.init()` **again**. Rustici rejects the re-init; pipwerks mishandles it and leaves `isActive` wrong. Every later `scorm.set()` silently no-ops.
4. Save-and-Exit → Rustici's rollup fires with only the initial `Set` events, no `exit=suspend` commit → defaults to `Rollup Completion = "completed"`.
5. Learner returns to **Completed** after seeing one page.

Two root causes: **(a)** multi-page architecture reloaded the SCO on every navigation (Rustici expects one init per session), and **(b)** no `<adlcp:masteryscore>` gave Rustici no explicit completion criterion, so its rollup-on-exit heuristic defaulted to complete. Fix = single-page SCO + `masteryscore=100`: one `LMSInitialize` so every `set()` persists, plus an explicit criterion (`score.raw >= 100`) only auto-completion satisfies.

A third, independent bug surfaced during the fix: the **pipwerks facade binding bug** (top-level aliases lose `this`, so `this.toBoolean` is undefined and the first `LMSInitialize` throws). Fixed by the binding patch above.

Debugging a similar completion issue: capture a HAR during a test session, decode the Rustici Runtime API payloads, and compare against this trace.

## Troubleshooting

**LMS rejects upload: "Invalid package"** (in order of likelihood): (1) zip has a nested folder — re-zip from inside the build dir; (2) `imsmanifest.xml` malformed — run `validate-scorm.py`; (3) a manifest `<file>` is missing from the zip; (4) `schemaversion` isn't `1.2`.

**Course marks complete on Save-and-Exit** (the bug this pipeline exists to avoid), on a NEW course: (1) confirm build output has NO `pages/` dir (`rm -rf scorm/build && rebuild`); (2) confirm `index.html` has `<template data-lesson-template="...">` entries; (3) confirm `<adlcp:masteryscore>100</adlcp:masteryscore>`; (4) confirm the pipwerks binding fix is applied; (5) capture a HAR and verify multiple commit POSTs (not just one at init), with the final carrying `exit=suspend` + `incomplete`. Older courses predating single-page must be migrated, not patched.

**Sidebar shows lessons visited on first launch** — the `localStorage` fallback wasn't stripped from `loadVisited`; when connected, `cmi.suspend_data` is the only source of truth.

**`Uncaught TypeError: this.toBoolean is not a function`** — the pipwerks facade aliases aren't `.bind(...)`ed; apply the binding fix.

**Completion doesn't mark complete in the LMS** — check devtools console for SCORM errors during an authenticated session; confirm `scorm.init()` returned true; confirm you `save()` after `set()`; inspect the HAR for the auto-completion commit carrying `lesson_status="completed"` + `score.raw="100"`.

## Checklist before upload

- [ ] All modules have `lesson.md` with passing lint.
- [ ] Eleventy build completes into a clean `scorm/build/` (no stale `pages/`).
- [ ] `imsmanifest.xml` includes `<adlcp:masteryscore>100</adlcp:masteryscore>`.
- [ ] Vendored pipwerks wrapper has `.bind(...)` on every convenience-facade alias.
- [ ] SCORM zip < 20 MB (host large media externally).
- [ ] Manifest validates (`scripts/validate-scorm.py`).
- [ ] Runtime tier passes (`npm --prefix tests/runtime test`): lessons navigate, last page with all pages visited marks complete, mid-course exit stays incomplete.
- [ ] `localStorage` fallback in `loadVisited` only triggers when NOT connected.
- [ ] Thumbnail produced (320×180, ≤100 KB).
- [ ] Training metadata prepared from `build/course-metadata.md`.
