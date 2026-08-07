/**
 * Runtime tier: load the BUILT package (the actual zip artifact) in jsdom
 * with a scorm-again SCORM 1.2 API stub standing in for the LMS, and
 * assert the LMS-visible behavior of the single-page SCO:
 *
 *   - LMSInitialize is called exactly once per session, across navigation
 *   - the scoring baseline (raw=0/min=0/max=100) and incomplete+suspend
 *     state are asserted at launch
 *   - completing every page (dwell + knowledge checks) auto-completes:
 *     lesson_status=completed, score.raw=100, committed
 *   - a mid-course exit leaves lesson_status=incomplete with exit=suspend
 *   - the manifest masteryscore is consistent with what the runtime reports
 *   - the cmi.core.lesson_location bookmark resumes to the right page
 *
 * No external services, no network. Requires the built package for the target course
 * (defaults to sample-course; override with the COURSE env var):
 *   scripts/build-scorm.sh "${COURSE:-sample-course}"
 *
 * Dwell timers: the course uses setTimeout(pageDwell * 1000). To keep the
 * suite fast we wrap window.setTimeout before the page scripts run and
 * scale down delays >= 1s. This only compresses time; ordering and logic
 * under test are unchanged.
 */

import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, existsSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { Scorm12API } from "scorm-again";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)), "..", ".."
);
// Course under test: defaults to sample-course, override with COURSE env var
// to run this tier against any course, matching lint-lessons.py /
// build-scorm.sh / validate-scorm.py's uniform course-name convention.
const COURSE = process.env.COURSE || "sample-course";
const zipPath = path.join(
  repoRoot, "courses", COURSE, "scorm", "dist", `${COURSE}.zip`
);

/** Divisor applied to setTimeout delays >= 1s (5s dwell -> 25ms). */
const DWELL_SCALE = 200;

let scoDir;
let server;
let baseUrl;

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".xml": "application/xml",
};

before(async () => {
  assert.ok(
    existsSync(zipPath),
    `built package missing: ${zipPath}\nbuild it first: scripts/build-scorm.sh ${COURSE}`
  );
  scoDir = mkdtempSync(path.join(tmpdir(), "sco-runtime-"));
  execFileSync("unzip", ["-q", zipPath, "-d", scoDir]);

  // jsdom refuses history.pushState on file:// URLs, and a real LMS serves
  // the SCO over HTTP anyway, so serve the extracted package on loopback.
  server = createServer((req, res) => {
    const relative = path
      .normalize(decodeURIComponent(new URL(req.url, "http://x").pathname))
      .replace(/^([/\\])+/, "");
    const file = path.join(scoDir, relative || "index.html");
    if (!file.startsWith(scoDir) || !existsSync(file)) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    res.writeHead(200, {
      "content-type": MIME[path.extname(file)] || "application/octet-stream",
    });
    res.end(readFileSync(file));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(() => {
  if (server) server.close();
});

/**
 * Launch the SCO in jsdom with a fresh scorm-again API installed as
 * window.API. `seed` pre-populates cmi values as if the LMS restored
 * them from a previous attempt.
 */
async function launchSco({ seed } = {}) {
  const api = new Scorm12API({ autocommit: false, logLevel: 4 });
  if (seed) {
    for (const [element, value] of Object.entries(seed)) {
      // Direct assignment on the cmi tree = "state restored by the LMS".
      const parts = element.split(".");
      let node = api.cmi;
      for (const p of parts.slice(1, -1)) node = node[p];
      node[parts[parts.length - 1]] = value;
    }
  }

  const calls = { LMSInitialize: 0, LMSFinish: 0, LMSCommit: 0 };
  for (const name of Object.keys(calls)) {
    const orig = api[name].bind(api);
    api[name] = (...args) => {
      calls[name] += 1;
      return orig(...args);
    };
  }

  const dom = await JSDOM.fromURL(`${baseUrl}/index.html`, {
    resources: "usable",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(window) {
      window.API = api;
      const origSetTimeout = window.setTimeout.bind(window);
      window.setTimeout = (fn, delay, ...args) =>
        origSetTimeout(
          fn,
          typeof delay === "number" && delay >= 1000 ? delay / DWELL_SCALE : delay,
          ...args
        );
    },
  });
  await new Promise((resolve) => dom.window.addEventListener("load", resolve));
  return { api, calls, window: dom.window, document: dom.window.document };
}

/**
 * Read the full cmi state including write-only elements (cmi.core.exit
 * throws on a direct getter read, faithfully to SCORM 1.2).
 */
function cmi(api) {
  return api.renderCMIToJSONObject().cmi;
}

function click(window, el) {
  assert.ok(el, "expected an element to click");
  el.dispatchEvent(
    new window.MouseEvent("click", { bubbles: true, cancelable: true })
  );
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(predicate, what, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await sleep(20);
  }
  assert.fail(`timed out waiting for: ${what}`);
}

/** Navigate to the next page, satisfying dwell + knowledge-check gating first. */
async function completeCurrentPageAndAdvance({ window, document }) {
  // Answer every knowledge check on the page (a page may have several,
  // and all must be correct before Next unlocks).
  for (const kc of document.querySelectorAll("#lesson-content .knowledge-check")) {
    if (kc.dataset.correct === "true") continue;
    click(window, kc.querySelector('.kc-option[data-correct="true"]'));
  }
  const next = document.getElementById("nav-next");
  await waitFor(
    () => !next.classList.contains("is-disabled"),
    "next button to unlock (dwell + knowledge checks)"
  );
  click(window, next);
}

test("LMSInitialize once; baseline score and incomplete+suspend at launch", async () => {
  const { api, calls } = await launchSco();
  assert.equal(calls.LMSInitialize, 1);
  const core = cmi(api).core;
  assert.equal(core.score.raw, "0");
  assert.equal(core.score.min, "0");
  assert.equal(core.score.max, "100");
  assert.equal(core.lesson_status, "incomplete");
  assert.equal(core.exit, "suspend");
  assert.ok(calls.LMSCommit >= 1, "launch state must be committed");
});

test("full walkthrough auto-completes with score 100, one session, one finish", async (t) => {
  const sco = await launchSco();
  const { api, calls, window, document } = sco;

  // Discover the full page order from the sidebar so the walkthrough
  // adapts to the authored course rather than a hard-coded page count.
  const slugs = [...document.querySelectorAll(".sidebar-page")].map(
    (el) => el.dataset.pageSlug
  );
  assert.ok(slugs.length >= 2, "course must have at least two pages");

  // Enter the course from the home view.
  click(window, document.querySelector(`[data-lesson-link="${slugs[0]}"]`));
  assert.equal(api.cmi.core.lesson_location, slugs[0]);

  // Walk every page in order, satisfying dwell + knowledge-check gating.
  for (const slug of slugs.slice(1)) {
    await completeCurrentPageAndAdvance(sco);
    assert.equal(api.cmi.core.lesson_location, slug);
  }

  // The last page is the course end: once its dwell elapses, every page
  // has been visited and the runtime must auto-complete.
  await waitFor(
    () => cmi(api).core.lesson_status === "completed",
    "auto-completion on the course-end page"
  );
  const core = cmi(api).core;
  assert.equal(core.score.raw, "100");
  assert.equal(core.exit, "");
  assert.equal(calls.LMSInitialize, 1, "no re-init across navigation");

  const commitsBeforeExit = calls.LMSCommit;
  assert.ok(commitsBeforeExit >= 1);

  window.dispatchEvent(new window.Event("beforeunload"));
  assert.equal(calls.LMSFinish, 1);
  assert.equal(cmi(api).core.lesson_status, "completed", "exit must not regress status");
});

test("mid-course exit leaves incomplete + suspend", async () => {
  const { api, calls, window, document } = await launchSco();
  click(window, document.querySelector('[data-lesson-link="module-1-page-01"]'));

  window.dispatchEvent(new window.Event("beforeunload"));
  assert.equal(calls.LMSFinish, 1);
  const core = cmi(api).core;
  assert.equal(core.lesson_status, "incomplete");
  assert.equal(core.exit, "suspend");
});

test("manifest masteryscore matches what completion reports", async () => {
  const manifest = readFileSync(path.join(scoDir, "imsmanifest.xml"), "utf8");
  const m = manifest.match(
    /<adlcp:masteryscore>\s*(\d+)\s*<\/adlcp:masteryscore>/
  );
  assert.ok(m, "manifest must declare adlcp:masteryscore");
  const masteryscore = Number(m[1]);
  assert.equal(masteryscore, 100, "completion strategy relies on masteryscore=100");
  // The runtime seeds max=100 and completion sets raw=100, so the mastery
  // comparison raw >= masteryscore can only be satisfied by finishing.
  assert.ok(masteryscore <= 100);
});

test("cmi.core.lesson_location bookmark resumes to the saved page", async () => {
  const { window, document } = await launchSco({
    seed: {
      "cmi.core.lesson_location": "module-1-page-02",
      "cmi.core.lesson_status": "incomplete",
    },
  });
  assert.equal(window.location.hash, "#module-1-page-02");
  await waitFor(
    () => !document.getElementById("lesson-view").hidden,
    "lesson view visible after bookmark resume"
  );
  const active = document.querySelector(".sidebar-page.is-active");
  assert.equal(active && active.dataset.pageSlug, "module-1-page-02");
});
