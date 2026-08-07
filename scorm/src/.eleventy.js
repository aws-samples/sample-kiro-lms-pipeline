/**
 * Eleventy configuration for the authored SCORM course.
 *
 * Responsibilities:
 *   - Load course.yaml as global data
 *   - Build a `lessonPages` collection from build/module-N/lesson.md files
 *     (outside Eleventy's normal input dir) paginated by {% nextPage %}
 *   - Provide shortcodes: tip, info, warning, objectives, knowledgeCheck,
 *     moduleEnd, dwell, nextPage
 *   - Render each page: Nunjucks (shortcodes) → markdown-it → HTML
 *   - Copy module visuals into assets/images/<module-id>/ and rewrite
 *     image paths in lesson content accordingly
 */

const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");
const MarkdownIt = require("markdown-it");

// COURSE_ROOT resolution
// ----------------------
// Set the ``COURSE_ROOT`` environment variable to point at the course's
// source tree. Everything under ``course.yaml`` + the referenced
// ``build/<module-id>/`` paths will be resolved relative to that root.
// Example:
//
//   COURSE_ROOT=/path/to/courses/sample-course npm run build
//
// The env var is the only mechanism - no config fallbacks. Unset means
// "course.yaml at the repo root" (two levels up from this file).
const DEFAULT_REPO_ROOT = path.resolve(__dirname, "../..");
const REPO_ROOT = process.env.COURSE_ROOT
  ? path.resolve(process.env.COURSE_ROOT)
  : DEFAULT_REPO_ROOT;
const COURSE_YAML = path.join(REPO_ROOT, "course.yaml");

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: false,
  breaks: false,
});

// Open external links (http/https) in a new tab so learners don't lose their
// place in the course. Internal anchor links and relative links remain default.
const defaultLinkOpen =
  md.renderer.rules.link_open ||
  function (tokens, idx, options, env, self) {
    return self.renderToken(tokens, idx, options);
  };

md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
  const token = tokens[idx];
  const hrefIdx = token.attrIndex("href");
  if (hrefIdx >= 0) {
    const href = token.attrs[hrefIdx][1] || "";
    if (/^https?:\/\//i.test(href)) {
      token.attrSet("target", "_blank");
      token.attrSet("rel", "noopener noreferrer");
    }
  }
  return defaultLinkOpen(tokens, idx, options, env, self);
};

function loadCourseConfig() {
  const raw = fs.readFileSync(COURSE_YAML, "utf8");
  return yaml.load(raw);
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function parseFrontmatter(raw) {
  const match = /^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/.exec(raw);
  if (!match) return { data: {}, body: raw };
  return { data: yaml.load(match[1]) || {}, body: match[2] };
}

// Lightweight inline-markdown handler for shortcode content (which is
// typically a sentence or two). Full markdown processing happens at the
// page level; this is just enough for callout bodies.
function mdInline(s) {
  // Delegate to markdown-it's inline renderer. Handles bold, italic, inline
  // code, links (which pick up our target="_blank" rule for external URLs),
  // and anything else markdown-it natively supports. Callouts and other
  // shortcodes that embed short author prose use this helper.
  return md.renderInline(String(s || "").trim());
}

// Recursively register passthrough-copy for image files under a visuals
// directory, preserving subdirectory structure but excluding caches,
// INDEX.md, captions.jsonl, and dotfiles.
const IMAGE_EXT = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]);

// Recursively collect the image files under a visuals directory and return
// their package-relative hrefs (assets/images/<module>/<subpath>). The SCORM
// manifest must declare every file shipped in the package under its resource,
// so these hrefs are emitted as <file> entries in imsmanifest.xml.
function collectImageHrefs(visualsDir, moduleId) {
  const hrefs = [];
  function walk(dir, relPrefix) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const rel = relPrefix ? `${relPrefix}/${entry.name}` : entry.name;
      const abs = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(abs, rel);
      } else if (IMAGE_EXT.has(path.extname(entry.name).toLowerCase())) {
        hrefs.push(`assets/images/${moduleId}/${rel}`);
      }
    }
  }
  walk(visualsDir, "");
  return hrefs;
}

module.exports = function (config) {
  const course = loadCourseConfig();

  config.addGlobalData("course", course.course);
  config.addGlobalData("modules", course.modules);
  config.addGlobalData("scormConfig", course.scorm || {});

  // -------------------------------------------------------------------------
  // Lesson collection
  // -------------------------------------------------------------------------

  config.addCollection("lessonPages", function () {
    const pages = [];
    for (const module of course.modules) {
      const lessonPath = path.join(REPO_ROOT, "build", module.id, "lesson.md");
      if (!fs.existsSync(lessonPath)) continue;

      const raw = fs.readFileSync(lessonPath, "utf8");
      const { data, body } = parseFrontmatter(raw);

      // Split on {% nextPage %} markers
      const segments = body.split(/\{%\s*nextPage\s*%\}/);
      segments.forEach((segment, idx) => {
        const pageNum = idx + 1;
        const slug = `${module.id}-page-${String(pageNum).padStart(2, "0")}`;
        // Extract first heading to use as sidebar label.
        // Prefer h2 (page-level), fall back to h1, fall back to a slug-derived title.
        const trimmed = segment.trim();
        const h2Match = /^##\s+(.+?)$/m.exec(trimmed);
        const h1Match = /^#\s+(.+?)$/m.exec(trimmed);
        const firstHeading = (h2Match && h2Match[1].trim()) ||
                             (h1Match && h1Match[1].trim()) ||
                             `Page ${pageNum}`;
        pages.push({
          slug,
          module_id: module.id,
          module_number: data.module_number || null,
          module_title: data.title || module.title,
          page_number: pageNum,
          total_pages_in_module: segments.length,
          is_first_page_of_module: pageNum === 1,
          is_last_page_of_module: pageNum === segments.length,
          first_heading: firstHeading,
          body: trimmed,
          frontmatter: data,
        });
      });
    }

    pages.forEach((p, i) => {
      p.overall_index = i;
      p.prev_slug = i > 0 ? pages[i - 1].slug : null;
      p.next_slug = i < pages.length - 1 ? pages[i + 1].slug : null;
      p.is_course_start = i === 0;
      p.is_course_end = i === pages.length - 1;
    });

    return pages;
  });

  // -------------------------------------------------------------------------
  // Shortcodes
  // -------------------------------------------------------------------------

  config.addPairedShortcode("tip", function (content, label) {
    const labelHtml = label ? `<span class="callout-topic">${escHtml(label)}</span>` : "";
    return `<aside class="callout callout-tip">
  <p class="callout-label">💡 Tip${labelHtml ? ` · ${labelHtml}` : ""}</p>
  <div class="callout-body">${mdInline(content)}</div>
</aside>`;
  });

  config.addPairedShortcode("info", function (content) {
    return `<aside class="callout callout-info">
  <p class="callout-label">ℹ️ Info</p>
  <div class="callout-body">${mdInline(content)}</div>
</aside>`;
  });

  config.addPairedShortcode("warning", function (content) {
    return `<aside class="callout callout-warning">
  <p class="callout-label">⚠️ Watch out</p>
  <div class="callout-body">${mdInline(content)}</div>
</aside>`;
  });

  // Renders frontmatter's learning_objectives as a styled block. The
  // objectives live on the page's `frontmatter` context (set by the
  // page template when it renders a lesson body). Each objective is
  // run through markdown-it's inline renderer so authors can use
  // **bold** and *italic* to draw attention to terms, and inline code
  // or links if useful.
  config.addShortcode("objectives", function (opts) {
    const fm = (this.ctx && this.ctx.frontmatter) || {};
    const objectives = (fm.learning_objectives || []).map(
      (o) => `    <li>${mdInline(o)}</li>`
    );
    if (objectives.length === 0) return `<!-- no objectives -->`;
    return `<section class="objectives">
  <h3>By the end of this module, you'll be able to:</h3>
  <ul>
${objectives.join("\n")}
  </ul>
</section>`;
  });

  config.addPairedShortcode("knowledgeCheck", function (content) {
    let data;
    try {
      data = yaml.load(content);
    } catch (e) {
      return `<!-- knowledgeCheck parse error: ${escHtml(e.message)} -->`;
    }
    // Question and option text allow inline markdown so authors can
    // emphasize terms with *italics* or **bold**. Feedback also supports
    // inline markdown — its rendered HTML is HTML-encoded so it can
    // safely travel in a data-feedback attribute, and course.js decodes
    // + renders it via innerHTML when an option is clicked.
    const question = mdInline(data.question || "(missing question)");
    const graded = data.graded === true ? "true" : "false";
    const options = (data.options || [])
      .map((opt, i) => {
        const correct = opt.correct === true ? "true" : "false";
        const feedback = escHtml(mdInline(opt.feedback || ""));
        const text = mdInline(opt.text || "");
        return `    <li>
      <button class="kc-option" data-correct="${correct}" data-feedback="${feedback}">
        <span class="kc-option-letter">${String.fromCharCode(65 + i)}.</span>
        <span class="kc-option-text">${text}</span>
      </button>
    </li>`;
      })
      .join("\n");
    return `<div class="knowledge-check" data-graded="${graded}">
  <p class="kc-question">${question}</p>
  <ul class="kc-options">
${options}
  </ul>
  <p class="kc-feedback" hidden></p>
</div>`;
  });

  config.addShortcode("moduleEnd", function () {
    return `<div class="module-end" data-module-end="true">
  <p class="module-end-marker">End of module</p>
</div>`;
  });

  config.addShortcode("dwell", function (seconds) {
    const n = parseInt(seconds, 10);
    if (isNaN(n) || n < 0) return "";
    return `<meta data-page-dwell="${n}" hidden>`;
  });

  // -------------------------------------------------------------------------
  // Filter: render a lesson body through Nunjucks then markdown.
  //
  // ``body`` is the raw lesson content between {% nextPage %} markers.
  // ``frontmatter`` is the lesson-level frontmatter (for ``{% objectives %}``).
  // ``moduleId`` is the owning module's id, used to rewrite image paths.
  //
  // The lesson body contains Nunjucks shortcodes AND markdown. We process
  // shortcodes first (Nunjucks render), then run the result through
  // markdown-it. This matches Eleventy's own template/markdown handling.
  //
  // Single-page SCO note: we also rewrite per-lesson image paths in this
  // filter, because every lesson body is inlined into index.html. The old
  // ``rewrite-image-paths`` transform used outputPath to recover module-id,
  // which doesn't work when N lesson bodies all render into one file. Here
  // we take ``moduleId`` directly from the lesson's page record and rewrite
  // ``visuals/...`` srcs to ``assets/images/<module>/...`` before returning.
  // Paths are ROOT-relative (no ``../``) because index.html lives at the
  // package root.
  // -------------------------------------------------------------------------

  config.addFilter("renderLessonBody", function (body, frontmatter, moduleId) {
    const text = body && typeof body === "object" && body.val ? body.val : String(body || "");
    // Render shortcodes through Nunjucks first.
    // this.env is the Nunjucks Environment in a Nunjucks filter context;
    // fall back gracefully if not present (e.g., when called from Liquid).
    let afterShortcodes = text;
    try {
      if (this && this.env && typeof this.env.renderString === "function") {
        const ctx = {
          frontmatter: frontmatter || (this.ctx && this.ctx.page && this.ctx.page.frontmatter) || {},
          // Expose ``moduleId`` into the Nunjucks render context so
          // shortcodes that need the module id can find it.
          moduleId: moduleId || null,
        };
        afterShortcodes = this.env.renderString(text, ctx);
      }
    } catch (e) {
      console.error("[renderLessonBody] Nunjucks render failed:", e.message);
      // Fall through with raw text; markdown-it will at least render
      // what it can.
    }
    let html = md.render(afterShortcodes);

    // Rewrite per-lesson image paths. Authors write
    // ``![](visuals/first-call-deck/slide-14.png)`` which becomes
    // ``<img src="visuals/first-call-deck/...">`` after markdown render.
    // The matching assets were copied to ``assets/images/<module>/...``
    // by the passthrough-copy registration above; rewrite the src so
    // it resolves correctly from the package-root index.html.
    if (moduleId) {
      html = html.replace(
        /(<img\s[^>]*src=")visuals\/([^"]+)(")/g,
        `$1assets/images/${moduleId}/$2$3`
      );
    }

    return html;
  });

  // -------------------------------------------------------------------------
  // Copy assets
  // -------------------------------------------------------------------------

  config.addPassthroughCopy({ "assets/css": "assets/css" });
  config.addPassthroughCopy({ "assets/js": "assets/js" });

  // Copy per-module visuals into assets/images/<module>/
  // Register the whole visuals/ directory as a single passthrough target
  // per module. This means new subfolders and files get picked up
  // automatically without needing to restart the dev server.
  //
  // Note: this also copies non-image files (captions.jsonl, INDEX.md)
  // into the build output, but nothing references them so it's harmless
  // and keeps the config simple.
  //
  // Only include modules whose lesson.md exists (skips modules not yet authored).
  const imageFiles = [];
  for (const module of course.modules) {
    const lessonPath = path.join(REPO_ROOT, "build", module.id, "lesson.md");
    if (!fs.existsSync(lessonPath)) continue;

    const modVisuals = path.join(REPO_ROOT, "build", module.id, "visuals");
    if (fs.existsSync(modVisuals)) {
      const targetRoot = path.join("assets", "images", module.id);
      config.addPassthroughCopy({ [modVisuals]: targetRoot });
      imageFiles.push(...collectImageHrefs(modVisuals, module.id));
    }
  }

  // Expose the shipped image hrefs so imsmanifest.xml.njk can declare a
  // <file> entry for each one (SCORM/IMS Content Packaging requires every
  // packaged file to be enumerated under its resource).
  config.addGlobalData("imageFiles", imageFiles);

  // -------------------------------------------------------------------------
  // Transform: (single-page SCO)
  //
  // Per-lesson image-path rewriting now happens inside ``renderLessonBody``
  // where each lesson body has its owning ``moduleId`` in context. The
  // previous outputPath-based transform doesn't work for the single-page
  // SCO because every lesson body renders into the same ``index.html``.
  // -------------------------------------------------------------------------

  // Tell Eleventy to watch the per-module lesson content even though it
  // lives outside the src/ input dir. Without this, edits to lesson.md,
  // and course.yaml don't trigger a dev-server rebuild.
  // Uses the same REPO_ROOT resolution as the top of this file so the
  // watcher tracks the active course when COURSE_ROOT is set.
  config.addWatchTarget(path.join(REPO_ROOT, "build"));
  config.addWatchTarget(path.join(REPO_ROOT, "course.yaml"));

  return {
    dir: {
      input: ".",
      includes: "_includes",
      data: "_data",
      output: "../build",
    },
    templateFormats: ["md", "njk", "html", "xml"],
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
  };
};
