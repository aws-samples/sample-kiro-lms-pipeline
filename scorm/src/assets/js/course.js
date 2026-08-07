/**
 * SCORM course runtime (single-page SCO)
 *
 * Architecture
 * ------------
 * The whole course is one HTML page. ``index.html`` includes every
 * lesson body as an inert ``<template data-lesson-template="{slug}">``
 * plus a home view and a lesson view. This file:
 *
 *   1. Initializes the SCORM session exactly once.
 *   2. Routes between views based on ``location.hash``:
 *        - empty or ``#``       -> home view (module cards)
 *        - ``#{lesson-slug}``   -> lesson view with that lesson active
 *   3. Swaps lesson content into ``#lesson-content`` by cloning the
 *      matching template. No iframe, no page navigation, no re-init.
 *   4. Records the current lesson slug via ``cmi.core.lesson_location``
 *      and the visited-pages set via ``cmi.suspend_data``.
 *   5. Commits after every navigation with explicit
 *      ``cmi.core.lesson_status = incomplete`` and
 *      ``cmi.core.exit = suspend`` until the course auto-completes.
 *
 * Why single-page
 * ---------------
 * The multi-page layout this replaces called ``LMSInitialize`` on every
 * navigation because each page was a separate HTML file with its own
 * script boot. Rustici rejects re-inits on an already-active session,
 * so ``pipwerks.SCORM.connection.isActive`` stayed false for every
 * page after the first and every ``set``/``save`` silently no-op'd.
 * The data the LMS received was just the initial init, then an exit
 * with no progress data, so Rustici's roll-up defaulted to ``completed``
 * regardless of what the manifest said.
 *
 * Completion policy
 * -----------------
 * ``cmi.core.lesson_status`` is ``completed`` only when the course
 * auto-completes (last page reached with every page's gating
 * satisfied). Every other state transition
 * is a suspend: we re-assert
 * ``cmi.core.lesson_status = "incomplete"`` plus
 * ``cmi.core.exit = "suspend"`` on every navigation commit, every
 * knowledge-check answer, and in the final ``teardown()``. Any
 * mid-course exit (platform's Save-and-Exit, tab close) leaves the
 * SCO in ``incomplete`` state.
 */

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Constants and module state
  // -------------------------------------------------------------------------

  /** localStorage key for visited-pages fallback when no LMS is attached. */
  const VISIT_STORAGE_KEY = "scorm-course-visited";

  /** Slug constant meaning "show the home view, no lesson active." */
  const HOME_SLUG = "__home__";

  /** pipwerks SCORM wrapper handle, or null if not loaded. */
  const scorm = (window.pipwerks && window.pipwerks.SCORM) || null;

  /** Whether we successfully called ``LMSInitialize``. */
  let connected = false;

  /** Lesson metadata indexed by slug, populated from #course-manifest. */
  const lessonIndex = Object.create(null);

  /** Ordered list of lesson slugs (authoring order across modules). */
  let lessonOrder = [];

  /** Total lesson count — cached for the progress counter. */
  let totalLessons = 0;

  /** The slug of the lesson currently rendered in the lesson view. */
  let currentSlug = null;

  /** Configured minimum dwell time in seconds, read from manifest. */
  let minPageDwellSeconds = 5;

  /**
   * Score written to ``cmi.core.score.raw`` on completion. Read from the
   * course manifest, which templates it from ``scorm.passing_score`` in
   * course.yaml — the same value the imsmanifest.xml masteryscore uses,
   * so the two cannot drift apart.
   */
  let passingScore = 100;

  /** Map of slug → boolean. True once the dwell timer has elapsed for that page. */
  const dwellSatisfied = Object.create(null);

  /** Active setTimeout ID for the current page's dwell timer, or null. */
  let dwellTimerId = null;

  // -------------------------------------------------------------------------
  // Course manifest bootstrap
  // -------------------------------------------------------------------------

  /**
   * Parse the JSON blob in ``#course-manifest`` into :data:`lessonIndex`
   * and :data:`lessonOrder`. Called once at boot. If the blob is missing
   * or malformed, we log and fall back to an empty manifest — the home
   * view still renders and lesson navigation is a no-op, which is a
   * reasonable failure mode for a dev-time regression.
   */
  function loadManifest() {
    const el = document.getElementById("course-manifest");
    if (!el) {
      console.warn("[course] #course-manifest not found; lessons unavailable");
      return;
    }
    let data;
    try {
      data = JSON.parse(el.textContent || "{}");
    } catch (e) {
      console.warn("[course] course manifest is not valid JSON:", e);
      return;
    }
    totalLessons = data.totalLessons || 0;
    minPageDwellSeconds = data.minPageDwellSeconds || 5;
    passingScore = data.passingScore || 100;
    const lessons = Array.isArray(data.lessons) ? data.lessons : [];
    lessonOrder = lessons.map((l) => l.slug);
    for (const l of lessons) {
      lessonIndex[l.slug] = l;
    }
  }

  // -------------------------------------------------------------------------
  // Visited-pages state (array of lesson slugs)
  // -------------------------------------------------------------------------

  /**
   * Load the visited-pages list. When connected to an LMS, the LMS is
   * the source of truth — we trust ``cmi.suspend_data`` even when it's
   * empty (that means "new attempt, no progress"). Falling back to
   * localStorage on a real session would surface stale visit markers
   * from a prior authoring test and confuse the learner.
   *
   * Only in preview mode (no LMS) do we read localStorage, so authors
   * can iterate on lesson content without losing their place on reload.
   */
  function loadVisited() {
    if (connected) {
      try {
        const raw = scorm.get("cmi.suspend_data") || "";
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (e) {
        return [];
      }
    }
    // Preview mode: fall back to localStorage so reloads preserve the
    // reading position.
    try {
      const raw = localStorage.getItem(VISIT_STORAGE_KEY) || "";
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  /**
   * Persist the visited-pages list. When connected to an LMS, the LMS
   * is the single source of truth — we write only ``cmi.suspend_data``
   * and leave localStorage alone. Writing to both risked leaking stale
   * state across attempts (preview localStorage surviving past an LMS
   * reset of the transcript).
   *
   * In preview mode we write to localStorage so authors can reload
   * without losing position.
   */
  function saveVisited(list) {
    const serialized = JSON.stringify(list);
    if (connected) {
      try {
        scorm.set("cmi.suspend_data", serialized);
      } catch (e) {
        /* no-op */
      }
      return;
    }
    try {
      localStorage.setItem(VISIT_STORAGE_KEY, serialized);
    } catch (e) {
      /* no-op */
    }
  }

  /**
   * Add ``slug`` to the visited set if not already present. Returns
   * true if the set changed.
   */
  function markVisited(slug) {
    if (!slug || slug === HOME_SLUG) return false;
    const visited = loadVisited();
    if (visited.indexOf(slug) !== -1) return false;
    visited.push(slug);
    saveVisited(visited);
    return true;
  }

  /**
   * Reflect the visited-pages set in the sidebar by setting
   * ``data-visited="true"`` on each matching ``.sidebar-page`` element.
   */
  function renderSidebarVisits() {
    const visited = loadVisited();
    const set = new Set(visited);
    document.querySelectorAll(".sidebar-page[data-page-slug]").forEach((li) => {
      const slug = li.dataset.pageSlug;
      if (set.has(slug)) {
        li.dataset.visited = "true";
      } else {
        delete li.dataset.visited;
      }
    });
  }

  // -------------------------------------------------------------------------
  // Dwell timer and gating logic
  // -------------------------------------------------------------------------

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

  /**
   * Start the dwell timer for the given page. If the page's dwell was
   * previously satisfied (learner returning), skip the timer and
   * immediately re-evaluate gating.
   *
   * @param {string} slug - The lesson slug to start timing
   */
  function startDwellTimer(slug) {
    cancelDwellTimer();

    // Already satisfied on a previous visit — no new timer needed
    if (dwellSatisfied[slug]) {
      checkGatingConditions(slug);
      return;
    }

    // Check for per-page dwell override via {% dwell N %} shortcode
    var pageDwell = minPageDwellSeconds;
    var dwellMeta = document.querySelector("#lesson-content meta[data-page-dwell]");
    if (dwellMeta) {
      var override = parseInt(dwellMeta.dataset.pageDwell, 10);
      if (!isNaN(override) && override >= 0) {
        pageDwell = override;
      }
    }

    dwellTimerId = setTimeout(function () {
      dwellTimerId = null;
      dwellSatisfied[slug] = true;
      // Only re-evaluate if we're still on this page
      if (currentSlug === slug) {
        checkGatingConditions(slug);
      }
    }, pageDwell * 1000);
  }

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
    var meta = lessonIndex[slug];
    if (!meta) return;

    // Module intro pages are exempt from all gating
    if (meta.isFirstPageOfModule) {
      enableNextButton();
      markVisitedAndUpdate(slug);
      return;
    }

    // Check dwell condition
    var dwellOk = dwellSatisfied[slug] === true;

    // Check KC condition: all .knowledge-check elements must have data-correct="true"
    var kcElements = document.querySelectorAll(
      "#lesson-content .knowledge-check"
    );
    var kcOk = true;
    if (kcElements.length > 0) {
      for (var i = 0; i < kcElements.length; i++) {
        if (kcElements[i].dataset.correct !== "true") {
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

  /**
   * Enable the Next button (and check whether the course auto-completes).
   */
  function enableNextButton() {
    var next = document.getElementById("nav-next");
    if (next && !next.hidden) {
      next.classList.remove("is-disabled");
      next.removeAttribute("aria-disabled");
      next.style.pointerEvents = "";
    }
    maybeAutoComplete();
  }

  /**
   * Disable the Next button so it is non-interactive.
   */
  function disableNextButton() {
    var next = document.getElementById("nav-next");
    if (next && !next.hidden) {
      next.classList.add("is-disabled");
      next.setAttribute("aria-disabled", "true");
      next.style.pointerEvents = "none";
    }
  }

  /**
   * Mark the page as visited and update sidebar indicators.
   * Deferred wrapper around the existing markVisited + renderSidebarVisits.
   */
  function markVisitedAndUpdate(slug) {
    markVisited(slug);
    renderSidebarVisits();
    maybeAutoComplete();
  }

  /**
   * Auto-complete the course when on the last page AND all pages
   * have been visited (gating satisfied for all). Completion fires
   * automatically; there is no manual Finish button.
   */
  function maybeAutoComplete() {
    var meta = lessonIndex[currentSlug];
    if (!meta || !meta.isCourseEnd) return;

    // Check if all pages are visited
    var visited = loadVisited();
    var allVisited = lessonOrder.every(function (s) {
      return visited.indexOf(s) !== -1;
    });

    if (allVisited) {
      markComplete();
      // Show a completion confirmation in the lesson content
      var container = document.getElementById("lesson-content");
      if (container) {
        var completionMsg = document.createElement("div");
        completionMsg.className = "course-complete-banner";
        var msgText = document.createElement("p");
        var strong = document.createElement("strong");
        strong.textContent = "Course complete!";
        msgText.appendChild(document.createTextNode("\u2705 "));
        msgText.appendChild(strong);
        msgText.appendChild(document.createTextNode(" Your progress has been recorded."));
        completionMsg.appendChild(msgText);
        container.appendChild(completionMsg);
      }
    }
  }

  // -------------------------------------------------------------------------
  // SCORM connection and exit-mode handling
  // -------------------------------------------------------------------------

  /**
   * Re-assert "learner is in progress and suspending" on the LMS. Set
   * on every navigation commit, knowledge-check answer, and the final
   * teardown, UNLESS the learner has explicitly finished the course.
   *
   * SCORM 1.2 semantics:
   *   cmi.core.lesson_status = "incomplete" - learner has not yet
   *     satisfied the completion criterion (masteryscore=100 in the
   *     manifest).
   *   cmi.core.exit = "suspend" - on LMSFinish, treat this as a pause,
   *     not a final exit. Rustici uses this to decide whether to roll
   *     the activity up to complete.
   */
  function markAsSuspend() {
    if (!connected) return;
    try {
      scorm.set("cmi.core.lesson_status", "incomplete");
      scorm.set("cmi.core.exit", "suspend");
    } catch (e) {
      /* older / non-compliant LMSs may reject; safe to ignore */
    }
  }

  /**
   * Commit to the LMS. Batches the ``set`` + ``save`` pair into one
   * helper so every commit in this file consistently re-asserts the
   * suspend flag first.
   */
  function commitSuspend() {
    if (!connected) return;
    markAsSuspend();
    try {
      scorm.save();
    } catch (e) {
      /* no-op */
    }
  }

  /**
   * Clear the exit mode. Called only by :func:`markComplete` as part of
   * auto-completion. An empty ``cmi.core.exit`` combined with
   * ``lesson_status = "completed"`` is the SCORM 1.2 idiom for
   * "this SCO is done for real."
   */
  function clearExitMode() {
    if (!connected) return;
    try {
      scorm.set("cmi.core.exit", "");
    } catch (e) {
      /* no-op */
    }
  }

  /**
   * Initialize the SCORM session. Runs exactly once per launch, at
   * ``DOMContentLoaded``. On success, sets :data:`connected` to true,
   * seeds the scoring baseline (raw=0, min=0, max=100), asserts
   * ``incomplete + suspend``, and commits.
   *
   * On a returning learner whose last session auto-completed the
   * course (lesson_status=completed), we preserve that state.
   */
  function initScorm() {
    if (!scorm) {
      console.info("[course] pipwerks not loaded — running in preview mode");
      return;
    }
    scorm.version = "1.2";
    try {
      connected = scorm.init();
    } catch (e) {
      // If the vendored SCORM wrapper itself throws (we've seen
      // ``TypeError: this.toBoolean is not a function`` when the facade
      // aliases lose their ``this`` binding), we must not crash the
      // whole course. Log and fall back to preview mode: the UI still
      // routes correctly, learners just won't get their progress
      // tracked by the LMS. That's preferable to a white screen.
      console.warn("[course] scorm.init() threw — falling back to preview mode:", e);
      connected = false;
      return;
    }
    if (!connected) {
      console.info("[course] SCORM API not found — running in preview mode");
      return;
    }
    console.info("[course] SCORM API connected");

    // Seed scoring baseline so the manifest's masteryscore=100 has
    // something to compare against. raw=0 means "below mastery" and
    // the LMS should keep the SCO as incomplete until auto-completion
    // sets raw=100.
    try {
      scorm.set("cmi.core.score.raw", "0");
      scorm.set("cmi.core.score.min", "0");
      scorm.set("cmi.core.score.max", "100");
    } catch (e) {
      /* no-op */
    }

    let status = "";
    try {
      status = scorm.get("cmi.core.lesson_status") || "";
    } catch (e) {
      status = "";
    }
    if (status !== "completed") {
      commitSuspend();
    }
  }

  /**
   * Mark the course complete. The ONLY path that writes
   * ``lesson_status = "completed"``. Fires automatically once the
   * last page is reached with all pages visited.
   */
  function markComplete() {
    if (!connected) return;
    clearExitMode();
    try {
      scorm.set("cmi.core.lesson_status", "completed");
      scorm.set("cmi.core.score.raw", String(passingScore));
      scorm.save();
    } catch (e) {
      /* no-op */
    }
    console.info("[course] marked complete");
  }

  /**
   * Final save and terminate. Runs on ``beforeunload``. Re-asserts
   * the suspend state one last time (unless already completed) so
   * the LMS's final view of our state is unambiguous.
   */
  function teardown() {
    if (!connected) return;
    try {
      if (scorm.get("cmi.core.lesson_status") !== "completed") {
        markAsSuspend();
      }
      scorm.save();
      scorm.quit();
    } catch (e) {
      /* no-op */
    }
  }

  // -------------------------------------------------------------------------
  // View routing
  // -------------------------------------------------------------------------

  /**
   * Read the target slug from ``location.hash``. Empty hash means
   * "home view"; a hash that matches a known lesson slug means
   * "lesson view with that lesson active". Unknown hashes fall back
   * to the home view.
   */
  function slugFromHash() {
    const h = (location.hash || "").replace(/^#/, "").trim();
    if (!h) return HOME_SLUG;
    if (h === HOME_SLUG) return HOME_SLUG;
    if (lessonIndex[h]) return h;
    return HOME_SLUG;
  }

  /**
   * Switch the body's ``data-view`` attribute, which the stylesheet
   * uses to show/hide the home and lesson views. Separate from the
   * lesson-content rendering so the transition is a single DOM write.
   */
  function setView(view) {
    document.body.dataset.view = view;
    const home = document.getElementById("home-view");
    const lesson = document.getElementById("lesson-view");
    if (view === "home") {
      if (home) home.hidden = false;
      if (lesson) lesson.hidden = true;
    } else {
      if (home) home.hidden = true;
      if (lesson) lesson.hidden = false;
    }
  }

  /**
   * Render a lesson by cloning its ``<template>`` into the lesson
   * container, updating the sidebar highlight, the lesson-footer
   * navigation state, and the progress counter.
   *
   * Records the lesson as visited (sidebar + suspend_data), sets
   * ``cmi.core.lesson_location``, commits with ``suspend``, and
   * scrolls the reading column back to the top so the learner
   * starts every lesson at the heading.
   *
   * Returns ``true`` if the lesson was rendered, ``false`` if the
   * slug is unknown (in which case the caller should route to home).
   */
  function renderLesson(slug) {
    const meta = lessonIndex[slug];
    const tpl = document.querySelector(
      '[data-lesson-template="' + cssEscape(slug) + '"]'
    );
    if (!meta || !tpl) {
      console.warn("[course] unknown lesson slug:", slug);
      return false;
    }

    const container = document.getElementById("lesson-content");
    if (!container) return false;
    container.setAttribute("aria-busy", "true");

    // Swap in a clone of the template's document fragment. Cloning
    // is what materializes the images/scripts inside the template
    // (they stayed inert while the template wasn't in the live DOM).
    const clone = tpl.content.cloneNode(true);
    container.replaceChildren(clone);
    container.setAttribute("aria-busy", "false");

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
      } catch (e) {
        /* no-op */
      }
    }
    commitSuspend();
    return true;
  }

  /**
   * Escape a string so it's safe to use inside a CSS attribute
   * selector. Our slugs are ``module-N-page-NN`` and safe as-is, but
   * ``CSS.escape`` is the right answer in general and cheap to call.
   * Falls back to the raw string on browsers without ``CSS.escape``
   * (none that matter today, but defensible).
   */
  function cssEscape(s) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(s);
    }
    // Fallback: escape characters that have special meaning in CSS selectors.
    // Covers the full set CodeQL expects: quotes, backslashes, and all
    // non-alphanumeric ASCII characters that could break a selector context.
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (ch) {
      return "\\" + ch;
    });
  }

  /**
   * Scroll the main lesson column to the top of the viewport. We
   * don't use ``window.scrollTo`` alone because the lesson container
   * can be its own scrolling region on narrower viewports.
   */
  function scrollLessonToTop() {
    const main = document.querySelector("#lesson-view main.lesson");
    if (main && typeof main.scrollTo === "function") {
      main.scrollTo(0, 0);
    }
    window.scrollTo(0, 0);
  }

  /**
   * Mark the given lesson's sidebar entry active, clear any previous
   * active entry, and expand the owning module's sidebar group.
   */
  function updateSidebarActive(slug, moduleId) {
    document.querySelectorAll(".sidebar-page.is-active").forEach((li) => {
      li.classList.remove("is-active");
    });
    const li = document.querySelector(
      '.sidebar-page[data-page-slug="' + cssEscape(slug) + '"]'
    );
    if (li) li.classList.add("is-active");

    document.querySelectorAll(".sidebar-module").forEach((mod) => {
      const isCurrent = mod.dataset.moduleId === moduleId;
      mod.classList.toggle("is-current", isCurrent);
      if (isCurrent) {
        mod.dataset.collapsed = "false";
      }
    });
  }

  /**
   * Update the prev / next buttons and the progress counter to reflect
   * the current lesson.
   */
  function updateLessonFooter(meta) {
    const prev = document.getElementById("nav-prev");
    const next = document.getElementById("nav-next");
    const progress = document.getElementById("nav-progress");

    if (prev) {
      if (meta.prevSlug) {
        prev.hidden = false;
        prev.href = "#" + meta.prevSlug;
        prev.setAttribute("data-lesson-link", meta.prevSlug);
        prev.classList.remove("is-disabled");
      } else {
        prev.hidden = true;
      }
    }

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

    if (progress) {
      progress.textContent =
        (meta.overallIndex + 1) + " / " + totalLessons;
    }
  }

  /**
   * Route to the view indicated by the current hash. Called at boot
   * and on every ``hashchange`` / ``popstate``. The browser-native
   * hash-based navigation gives us back/forward button support for
   * free; we only have to react to it.
   */
  function route() {
    const slug = slugFromHash();
    if (slug === HOME_SLUG) {
      currentSlug = null;
      setView("home");
      return;
    }
    const ok = renderLesson(slug);
    if (ok) {
      setView("lesson");
    } else {
      // Unknown slug -> drop back to home without leaving a broken
      // hash in the URL.
      setView("home");
      if (location.hash) {
        history.replaceState(null, "", location.pathname + location.search);
      }
    }
  }

  /**
   * Navigate to the given slug (or ``HOME_SLUG``). Uses ``history.pushState``
   * to update the URL without a page reload, then runs :func:`route`.
   * Centralizing the navigation here means every navigation path
   * (card click, sidebar click, prev/next, programmatic) takes the
   * same code path and fires the same commit.
   */
  function navigateTo(slug) {
    const targetHash = slug === HOME_SLUG ? "" : "#" + slug;
    const targetUrl = location.pathname + location.search + targetHash;
    if (location.hash !== targetHash) {
      history.pushState({ slug: slug }, "", targetUrl);
    }
    route();
  }

  // -------------------------------------------------------------------------
  // Click / keyboard delegation
  // -------------------------------------------------------------------------

  /**
   * Handle any click on an element carrying ``data-lesson-link``.
   * Covers module-card "Start this module" links, sidebar entries,
   * prev/next buttons, and the in-lesson "Back to overview" link.
   * Falls through to the browser default for anything else (including
   * image lightboxes, external docs, anchor jumps inside a lesson).
   */
  function handleLessonLinkClick(e) {
    const el = e.target.closest("[data-lesson-link]");
    if (!el) return;
    // Respect modifier-click (open in new tab etc.) — do nothing, let
    // the browser follow the href. For a single-page SCO a new tab
    // would just re-launch the same hash, which is fine.
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

  /**
   * Toggle the collapsed/expanded state of a sidebar module group.
   */
  function handleSidebarToggle(e) {
    const btn = e.target.closest("[data-module-toggle]");
    if (!btn) return;
    const moduleEl = btn.closest(".sidebar-module");
    if (!moduleEl) return;
    const collapsed = moduleEl.dataset.collapsed === "true";
    moduleEl.dataset.collapsed = collapsed ? "false" : "true";
  }

  /**
   * Knowledge-check click handler. On correct answer: lock options and
   * set data-correct="true". On incorrect: show feedback but keep
   * options enabled for retry. After any answer, re-evaluate gating.
   */
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
      feedback.textContent = btn.dataset.feedback || "";
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

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------

  function boot() {
    loadManifest();
    initScorm();

    // If the LMS remembers where we left off, jump straight there.
    // The bookmark is in ``cmi.core.lesson_location`` (set on every
    // navigation). Only override an empty hash — if the URL already
    // has a hash, the author explicitly linked in and we respect
    // that.
    if (connected && !location.hash) {
      let bookmark = "";
      try {
        bookmark = scorm.get("cmi.core.lesson_location") || "";
      } catch (e) {
        bookmark = "";
      }
      if (bookmark && lessonIndex[bookmark]) {
        history.replaceState(
          { slug: bookmark },
          "",
          location.pathname + location.search + "#" + bookmark
        );
      }
    }

    route();

    // Apply any already-visited markers to the sidebar. ``renderLesson``
    // does this too, but we also want the home-view -> sidebar to
    // reflect past progress if the learner is in lesson view later.
    renderSidebarVisits();

    document.addEventListener("click", handleLessonLinkClick);
    document.addEventListener("click", handleSidebarToggle);
    document.addEventListener("click", handleKnowledgeCheck);

    window.addEventListener("popstate", route);
    window.addEventListener("hashchange", route);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.addEventListener("beforeunload", teardown);
})();
