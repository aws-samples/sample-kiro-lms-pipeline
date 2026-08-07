# Implementation Plan: Page Dwell Time + Knowledge Check Gating

> status: implemented — the gating engine (tasks 1 and 2) is shipped in `scorm/src/assets/js/course.js` (`minPageDwellSeconds`, `dwellSatisfied`, `dwellTimerId`, `startDwellTimer`, `checkGatingConditions`) and exercised by `courses/sample-course/build/module-3/lesson.md` (`{% dwell 0 %}`) and the runtime test tier (`tests/runtime/sco-runtime.test.mjs`). Task 3 is a manual verification checkpoint; the optional property tests in task 4 (marked `*`) were not written.
>
> There is no manual Finish button: completion fires automatically once the learner reaches the last page with every page's gating satisfied (all pages visited), via the `maybeAutoComplete()` function. `requirements.md` (Requirement 7), `design.md` (Property 12 and the `maybeAutoComplete()` component) describe this shipped behavior. The task 2.1 / 2.4 references below still name the historical `updateFinishButton()` helper (renamed to `maybeAutoComplete()`) and the removed `#nav-finish` button; read them as the auto-completion path.

## Overview

Add dwell-timer and knowledge-check gating to the SCORM course engine. The Next button stays disabled until the learner has spent the configured minimum time on a page AND answered all knowledge checks correctly. Module intro pages are exempt. Pages only count as "visited" once gating conditions are satisfied.

## Tasks

- [x] 1. Add manifest metadata (build-time config)
  - [x] 1.1 Add `min_page_dwell_seconds` to course.yaml and emit it in the manifest template
    - Add `min_page_dwell_seconds: 5` to the `scorm:` section of the course's `course.yaml`
    - In `scorm/src/index.njk`, add `"minPageDwellSeconds": {{ scormConfig.min_page_dwell_seconds or 5 }}` to the `#course-manifest` JSON object (top-level, before `"lessons"`)
    - In `scorm/src/index.njk`, add `"isFirstPageOfModule": {% if page.is_first_page_of_module %}true{% else %}false{% endif %}` to each lesson entry in the manifest JSON
    - _Requirements: 1.1, 1.2, 1.3, 3.1_

- [x] 2. Implement gating logic in course.js
  - [x] 2.1 Add module-level state and helper functions for dwell timer and gating
    - Add `minPageDwellSeconds`, `dwellSatisfied`, `dwellTimerId` module-level variables
    - Extend `loadManifest()` to read `minPageDwellSeconds` from the parsed manifest data
    - Add `startDwellTimer(slug)`, `cancelDwellTimer()`, `checkGatingConditions(slug)` functions
    - Add `enableNextButton()`, `disableNextButton()`, `markVisitedAndUpdate(slug)`, `updateFinishButton()` functions
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.2, 3.3, 4.4, 4.5, 5.1, 5.2, 5.3, 7.1, 7.2_

  - [x] 2.2 Modify `renderLesson()` to use gating instead of immediate `markVisited`
    - Remove the direct `markVisited(slug)` and `renderSidebarVisits()` calls
    - Add `disableNextButton()` + `cancelDwellTimer()` at the start of each render
    - Call `checkGatingConditions(slug)` which handles exempt pages, dwell timer start, and KC evaluation
    - _Requirements: 2.1, 3.2, 5.1, 6.2_

  - [x] 2.3 Modify `handleKnowledgeCheck()` to support retry and trigger gating re-evaluation
    - On incorrect answer: show feedback but keep options enabled for retry (do not disable buttons)
    - On correct answer: lock options (disable buttons), set `data-correct="true"`
    - After any answer, call `checkGatingConditions(currentSlug)` to re-evaluate
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 2.4 Modify `handleLessonLinkClick()` and `updateLessonFooter()` for disabled Next button
    - In `handleLessonLinkClick()`: block navigation when `#nav-next` has `is-disabled` class
    - In `updateLessonFooter()`: remove the `next.classList.remove("is-disabled")` line so gating controls enabled state; hide Finish by default (let `updateFinishButton()` manage it)
    - _Requirements: 2.2, 6.1, 7.1_

- [ ] 3. Checkpoint — Verify gating behavior
  - Ensure all tests pass, ask the user if questions arise.
  - Manually verify: Next button disabled on page load, enabled after dwell time elapses, module intro pages are exempt, KC retry works, Finish button appears only when all pages visited.

- [ ]* 4. Write property tests for gating logic
  - [ ]* 4.1 Write property test for dwell timer and Next button state
    - **Property 2: Next button disabled while dwell timer active**
    - **Property 3: Next button enabled when sole gating condition (dwell) elapses**
    - **Validates: Requirements 2.2, 2.3**

  - [ ]* 4.2 Write property test for module intro page exemption
    - **Property 6: Module intro pages are exempt from all gating**
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 4.3 Write property test for KC gating and combined conditions
    - **Property 7: KC gating requires all knowledge checks correct**
    - **Property 9: Combined gating requires both dwell AND KC**
    - **Validates: Requirements 4.1, 4.5**

  - [ ]* 4.4 Write property test for visited-set integrity
    - **Property 10: Page not visited until all gating conditions satisfied**
    - **Property 4: Dwell timer cancelled on navigation away**
    - **Validates: Requirements 5.1, 2.5, 6.3**

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The implementation language is JavaScript (vanilla, no framework) matching the existing `course.js`
- `.eleventy.js` already computes `is_first_page_of_module` — no changes needed there
- The `scormConfig` global data is already exposed by `.eleventy.js` via `config.addGlobalData("scormConfig", course.scorm || {})`
- Property tests validate universal correctness properties from the design document
- The existing `cmi.suspend_data` format (JSON array of slugs) is unchanged; only the timing of when slugs are added changes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4"] }
  ]
}
```
