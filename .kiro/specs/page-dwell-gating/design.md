# Design Document: Page Dwell Time + Knowledge Check Gating

## Overview

This feature adds two gating conditions to the SCORM course engine's "Next" button: a configurable minimum page dwell time and knowledge check correctness verification. Both conditions must be satisfied before the learner can advance and before a page counts as "visited" for completion tracking.

The implementation is entirely client-side within `scorm/src/assets/js/course.js`, with a small build-time change to the Eleventy config (`.eleventy.js`) and the `index.njk` template to emit additional metadata into the course manifest JSON.

## Architecture

### Component Interaction

```
┌─────────────────────────────────────────────────────────────┐
│  course.yaml (author config)                                │
│    scorm.min_page_dwell_seconds: 5                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ (build time)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  .eleventy.js                                               │
│    - Reads min_page_dwell_seconds from scormConfig          │
│    - Emits isFirstPageOfModule per lesson in manifest        │
│    - Emits minPageDwellSeconds in manifest                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ (rendered into index.html)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  #course-manifest JSON                                      │
│    { minPageDwellSeconds: 5,                                │
│      lessons: [{ slug, isFirstPageOfModule, ... }] }        │
└──────────────────────┬──────────────────────────────────────┘
                       │ (parsed at boot)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  course.js (runtime)                                        │
│                                                             │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ Dwell Timer │  │ KC Gating Logic  │  │ checkGating() │  │
│  │  Module     │  │  (in handleKC)   │  │  Orchestrator │  │
│  └──────┬──────┘  └────────┬─────────┘  └───────┬───────┘  │
│         │                  │                     │           │
│         └──────────────────┴─────────────────────┘           │
│                            │                                 │
│                            ▼                                 │
│              ┌─────────────────────────┐                     │
│              │  Next Button State      │                     │
│              │  markVisited() call     │                     │
│              │  Auto-completion logic  │                     │
│              └─────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Build time**: `.eleventy.js` reads `scormConfig.min_page_dwell_seconds` (defaulting to 5) and each lesson's `is_first_page_of_module` flag. These are emitted into the `#course-manifest` JSON blob.

2. **Boot**: `loadManifest()` parses the manifest and stores `minPageDwellSeconds` at module scope and `isFirstPageOfModule` per lesson entry in `lessonIndex`.

3. **Page render**: `renderLesson(slug)` calls `checkGatingConditions(slug)` instead of immediately calling `markVisited()`. The Next button starts disabled.

4. **Dwell timer**: A `setTimeout` fires after `minPageDwellSeconds * 1000` ms, sets `dwellSatisfied[slug] = true`, and re-evaluates gating.

5. **KC interaction**: `handleKnowledgeCheck()` checks if the answer is correct. If incorrect, options are re-enabled for retry. If correct, it re-evaluates gating.

6. **Gating evaluation**: `checkGatingConditions(slug)` checks both `dwellSatisfied[slug]` and all `.knowledge-check[data-correct="true"]` on the page. When both pass, it enables the Next button and calls `markVisited(slug)`.

## Components

### Module-Level State (in `course.js`)

```javascript
/** Configured minimum dwell time in seconds, read from manifest. */
let minPageDwellSeconds = 5;

/** Map of slug → boolean. True once the dwell timer has elapsed for that page. */
const dwellSatisfied = Object.create(null);

/** Active setTimeout ID for the current page's dwell timer, or null. */
let dwellTimerId = null;
```

### Build-Time Changes

#### `.eleventy.js` — Manifest Data

The `lessonPages` collection already computes `is_first_page_of_module`. No change needed there. The manifest JSON template in `index.njk` needs two additions:

1. A top-level `minPageDwellSeconds` field read from `scormConfig.min_page_dwell_seconds` (default 5).
2. An `isFirstPageOfModule` field per lesson entry.

#### `index.njk` — Manifest JSON Template

```javascript
// Inside the #course-manifest <script> block:
{
  "totalLessons": {{ collections.lessonPages.length }},
  "minPageDwellSeconds": {{ scormConfig.min_page_dwell_seconds or 5 }},
  "lessons": [
    {%- for page in collections.lessonPages %}
    {
      "slug": "{{ page.slug }}",
      "moduleId": "{{ page.module_id }}",
      "overallIndex": {{ page.overall_index }},
      "prevSlug": {% if page.prev_slug %}"{{ page.prev_slug }}"{% else %}null{% endif %},
      "nextSlug": {% if page.next_slug %}"{{ page.next_slug }}"{% else %}null{% endif %},
      "isCourseEnd": {% if page.is_course_end %}true{% else %}false{% endif %},
      "isFirstPageOfModule": {% if page.is_first_page_of_module %}true{% else %}false{% endif %},
      "firstHeading": {{ page.first_heading | dump | safe }}
    }{% if not loop.last %},{% endif %}
    {%- endfor %}
  ]
}
```

### Runtime Functions (in `course.js`)

#### `loadManifest()` — Extended

```javascript
function loadManifest() {
  // ... existing parsing ...
  minPageDwellSeconds = data.minPageDwellSeconds || 5;
  // ... existing lesson loop, now also storing isFirstPageOfModule:
  for (const l of lessons) {
    lessonIndex[l.slug] = l; // l now includes isFirstPageOfModule
  }
}
```

#### `checkGatingConditions(slug)` — New Orchestrator

```javascript
/**
 * Evaluate whether all gating conditions for the current page are
 * satisfied. If so, enable the Next button and mark the page visited.
 * Called:
 *   - After dwell timer elapses
 *   - After a knowledge check is answered correctly
 *   - On initial render (for exempt pages)
 *
 * @param {string} slug - The current lesson slug
 */
function checkGatingConditions(slug) {
  const meta = lessonIndex[slug];
  if (!meta) return;

  // Module intro pages are exempt from all gating
  if (meta.isFirstPageOfModule) {
    enableNextButton();
    markVisitedAndUpdate(slug);
    return;
  }

  // Check dwell condition
  const dwellOk = dwellSatisfied[slug] === true;

  // Check KC condition: all .knowledge-check elements must have data-correct="true"
  const kcElements = document.querySelectorAll(
    "#lesson-content .knowledge-check"
  );
  let kcOk = true;
  if (kcElements.length > 0) {
    for (const kc of kcElements) {
      if (kc.dataset.correct !== "true") {
        kcOk = false;
        break;
      }
    }
  }

  if (dwellOk && kcOk) {
    enableNextButton();
    markVisitedAndUpdate(slug);
  }
}
```

#### `startDwellTimer(slug)` — New

```javascript
/**
 * Start the dwell timer for the given page. If the page's dwell was
 * previously satisfied (learner returning), skip the timer and
 * immediately re-evaluate gating.
 *
 * @param {string} slug - The lesson slug to start timing
 */
function startDwellTimer(slug) {
  // Cancel any lingering timer from a previous page
  cancelDwellTimer();

  // Already satisfied on a previous visit — no new timer needed
  if (dwellSatisfied[slug]) {
    checkGatingConditions(slug);
    return;
  }

  dwellTimerId = setTimeout(function () {
    dwellTimerId = null;
    dwellSatisfied[slug] = true;
    // Only re-evaluate if we're still on this page
    if (currentSlug === slug) {
      checkGatingConditions(slug);
    }
  }, minPageDwellSeconds * 1000);
}
```

#### `cancelDwellTimer()` — New

```javascript
/**
 * Cancel the active dwell timer, if any. Called when the learner
 * navigates away from a page before the timer elapses.
 */
function cancelDwellTimer() {
  if (dwellTimerId !== null) {
    clearTimeout(dwellTimerId);
    dwellTimerId = null;
  }
}
```

#### `enableNextButton()` / `disableNextButton()` — New

```javascript
/**
 * Enable the Next button (and auto-complete the course if on the last
 * page with all pages visited).
 */
function enableNextButton() {
  const next = document.getElementById("nav-next");
  if (next && !next.hidden) {
    next.classList.remove("is-disabled");
    next.removeAttribute("aria-disabled");
    next.style.pointerEvents = "";
  }
  // Also check whether the course should auto-complete
  maybeAutoComplete();
}

/**
 * Disable the Next button so it is non-interactive.
 */
function disableNextButton() {
  const next = document.getElementById("nav-next");
  if (next && !next.hidden) {
    next.classList.add("is-disabled");
    next.setAttribute("aria-disabled", "true");
    next.style.pointerEvents = "none";
  }
}
```

#### `markVisitedAndUpdate(slug)` — New

```javascript
/**
 * Mark the page as visited and update sidebar indicators.
 * Deferred wrapper around the existing markVisited + renderSidebarVisits.
 */
function markVisitedAndUpdate(slug) {
  markVisited(slug);
  renderSidebarVisits();
  maybeAutoComplete();
}
```

#### `maybeAutoComplete()` — New

```javascript
/**
 * Auto-complete the course when on the last page AND all pages have
 * been visited (gating satisfied for all). Completion fires
 * automatically; there is no manual Finish button.
 */
function maybeAutoComplete() {
  const meta = lessonIndex[currentSlug];
  if (!meta || !meta.isCourseEnd) return;

  // Check if all pages are visited
  const visited = loadVisited();
  const allVisited = lessonOrder.every(
    (s) => visited.indexOf(s) !== -1
  );

  if (allVisited) {
    markComplete();
    // Show a completion confirmation in the lesson content
  }
}
```

### Modified `renderLesson(slug)`

The key change: instead of calling `markVisited(slug)` and `renderSidebarVisits()` immediately, we:

1. Disable the Next button on entry
2. Cancel any previous dwell timer
3. Start a new dwell timer (or skip for exempt pages)
4. Call `checkGatingConditions(slug)` which handles the rest

```javascript
function renderLesson(slug) {
  // ... existing template cloning logic ...

  currentSlug = slug;
  updateSidebarActive(slug, meta.moduleId);
  updateLessonFooter(meta);
  scrollLessonToTop();

  // --- GATING: replaces immediate markVisited + renderSidebarVisits ---
  disableNextButton();
  cancelDwellTimer();

  if (meta.isFirstPageOfModule) {
    // Exempt: immediately satisfy all conditions
    checkGatingConditions(slug);
  } else {
    startDwellTimer(slug);
    // Also check immediately in case dwell was previously satisfied
    // and there are no KCs (or all KCs were already answered)
    checkGatingConditions(slug);
  }
  // --- END GATING ---

  if (connected) {
    try {
      scorm.set("cmi.core.lesson_location", slug);
    } catch (e) { /* no-op */ }
  }
  commitSuspend();
  return true;
}
```

### Modified `handleKnowledgeCheck(e)`

The KC handler changes to support retry on incorrect answers and to trigger gating re-evaluation on correct answers:

```javascript
function handleKnowledgeCheck(e) {
  const btn = e.target.closest(".kc-option");
  if (!btn) return;
  const kc = btn.closest(".knowledge-check");
  if (!kc) return;

  // If already answered correctly, lock it (no further interaction)
  if (kc.dataset.correct === "true") return;

  const isCorrect = btn.dataset.correct === "true";

  if (isCorrect) {
    // Lock options on correct answer
    kc.querySelectorAll(".kc-option").forEach((b) => {
      b.setAttribute("disabled", "true");
    });
    btn.dataset.selected = "true";
    kc.dataset.answered = "true";
    kc.dataset.correct = "true";
  } else {
    // Show feedback but allow retry: clear previous selection,
    // keep options enabled
    kc.querySelectorAll(".kc-option").forEach((b) => {
      delete b.dataset.selected;
    });
    btn.dataset.selected = "true";
    kc.dataset.answered = "true";
    kc.dataset.correct = "false";
  }

  // Show feedback
  const feedback = kc.querySelector(".kc-feedback");
  if (feedback) {
    feedback.innerHTML = btn.dataset.feedback || "";
    feedback.hidden = false;
    feedback.classList.toggle("correct", isCorrect);
    feedback.classList.toggle("incorrect", !isCorrect);
  }

  if (kc.dataset.graded === "true") {
    commitSuspend();
  }

  // Re-evaluate gating conditions
  if (currentSlug) {
    checkGatingConditions(currentSlug);
  }
}
```

### Modified `handleLessonLinkClick(e)`

The click handler for `[data-lesson-link]` elements needs to respect the disabled state of the Next button:

```javascript
function handleLessonLinkClick(e) {
  const el = e.target.closest("[data-lesson-link]");
  if (!el) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  if (e.defaultPrevented) return;

  // Block navigation via the Next button when it's disabled (gated)
  if (el.id === "nav-next" && el.classList.contains("is-disabled")) {
    e.preventDefault();
    return;
  }

  e.preventDefault();
  navigateTo(el.dataset.lessonLink);
}
```

### Modified `updateLessonFooter(meta)`

The footer update no longer unconditionally enables the Next button. It sets visibility but leaves the enabled/disabled state to the gating logic:

```javascript
function updateLessonFooter(meta) {
  // ... prev button logic unchanged ...

  if (next) {
    if (meta.nextSlug) {
      next.hidden = false;
      next.href = "#" + meta.nextSlug;
      next.setAttribute("data-lesson-link", meta.nextSlug);
      // Do NOT remove is-disabled here — gating controls that
    } else {
      next.hidden = true;
    }
  }

  // There is no Finish button; completion fires automatically via
  // maybeAutoComplete() once all pages are visited.

  // ... progress counter unchanged ...
}
```

## Interfaces

### Manifest JSON Schema (Extended)

```typescript
interface CourseManifest {
  totalLessons: number;
  minPageDwellSeconds: number; // NEW — default 5
  lessons: LessonEntry[];
}

interface LessonEntry {
  slug: string;
  moduleId: string;
  overallIndex: number;
  prevSlug: string | null;
  nextSlug: string | null;
  isCourseEnd: boolean;
  isFirstPageOfModule: boolean; // NEW
  firstHeading: string;
}
```

### Gating State (Module-Level Variables)

```typescript
// Conceptual types for the module-level state
type DwellSatisfiedMap = Record<string, boolean>;
// dwellSatisfied: DwellSatisfiedMap — keyed by slug
// dwellTimerId: number | null — active setTimeout ID
// minPageDwellSeconds: number — from manifest
```

## Data Models

No persistent data model changes. The `cmi.suspend_data` format (JSON array of visited slugs) remains unchanged. The only difference is *when* slugs are added — deferred until gating conditions pass rather than on render.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `minPageDwellSeconds` missing from manifest | Default to 5 seconds |
| `isFirstPageOfModule` missing from a lesson entry | Treat as `false` (apply normal gating) |
| `setTimeout` not available (impossible in browsers) | Dwell condition immediately satisfied |
| Learner closes tab mid-dwell | Timer cancelled by page unload; page not marked visited; resume picks up from `cmi.suspend_data` |
| No `.knowledge-check` elements on page | KC condition is trivially satisfied; only dwell gates |
| Multiple KCs on one page | All must be `data-correct="true"` before KC condition passes |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Dwell timer starts on non-exempt page render

*For any* lesson page that is not a module intro page (`isFirstPageOfModule === false`), rendering that page SHALL result in an active dwell timer with the configured duration.

**Validates: Requirements 2.1**

### Property 2: Next button disabled while dwell timer active

*For any* lesson page with an active (unsatisfied) dwell timer, the Next button SHALL be in a disabled state (has `is-disabled` class and `aria-disabled="true"`).

**Validates: Requirements 2.2**

### Property 3: Next button enabled when sole gating condition (dwell) elapses

*For any* lesson page that has no knowledge check elements and whose dwell timer has elapsed, the Next button SHALL be in an enabled state.

**Validates: Requirements 2.3**

### Property 4: Dwell timer cancelled on navigation away

*For any* lesson page with an active dwell timer, when the learner navigates to a different page, the timer SHALL be cancelled (no lingering timeout) and the page SHALL NOT be added to the visited set.

**Validates: Requirements 2.5, 6.3**

### Property 5: Previously-satisfied dwell is remembered

*For any* lesson page whose dwell condition was previously satisfied (`dwellSatisfied[slug] === true`), re-rendering that page SHALL immediately treat the dwell condition as satisfied without starting a new timer.

**Validates: Requirements 2.6**

### Property 6: Module intro pages are exempt from all gating

*For any* lesson page with `isFirstPageOfModule === true`, rendering that page SHALL immediately enable the Next button AND add the page to the visited set, without requiring any dwell time or knowledge check interaction.

**Validates: Requirements 3.2, 3.3**

### Property 7: KC gating requires all knowledge checks correct

*For any* lesson page containing K knowledge check elements (K ≥ 1), the Next button SHALL remain disabled until all K elements have `data-correct="true"`, regardless of the dwell timer state.

**Validates: Requirements 4.1**

### Property 8: Incorrect KC answer allows retry

*For any* knowledge check element where the learner selects an incorrect answer, the option buttons SHALL remain interactive (not disabled) so the learner can select a different option.

**Validates: Requirements 4.2, 4.3**

### Property 9: Combined gating requires both dwell AND KC

*For any* lesson page that has both a dwell timer requirement and one or more knowledge check elements, the Next button SHALL be enabled if and only if the dwell condition is satisfied AND all knowledge checks have `data-correct="true"`.

**Validates: Requirements 4.4, 4.5**

### Property 10: Page not visited until all gating conditions satisfied

*For any* lesson page, the page slug SHALL NOT appear in the visited set until all applicable gating conditions (dwell elapsed, all KCs correct) are satisfied. Conversely, once all conditions are satisfied, the slug SHALL be added to the visited set.

**Validates: Requirements 5.1, 5.2**

### Property 11: Gating applies independently per page navigation

*For any* non-exempt lesson page navigated to (whether via sidebar, Next button, or direct hash), the gating conditions SHALL be evaluated independently for that page — the dwell timer starts fresh (unless previously satisfied) and KC state is read from the current DOM.

**Validates: Requirements 6.2**

### Property 12: Auto-completion requires all pages visited with gating satisfied

*For any* state where the learner is on the last page (`isCourseEnd === true`), the course SHALL be marked complete if and only if the visited set contains ALL lesson slugs (meaning all pages have had their gating conditions satisfied at some point). Completion fires automatically; there is no manual Finish button.

**Validates: Requirements 7.1, 7.2**
