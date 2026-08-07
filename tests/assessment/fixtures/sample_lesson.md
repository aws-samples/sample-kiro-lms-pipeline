---
title: "The Authoring Pipeline"
module: module-1
---

# The Authoring Pipeline

Welcome to the first module. This lesson explains how a markdown lesson
file becomes a single-page SCORM package that any LMS can play.

## From Markdown to Package

The build script reads each module's `lesson.md`, splits it into pages at
every `##` heading, and renders the pages into one `index.html`. The SCORM
runtime then reports progress to the LMS through the SCORM 1.2 API.

{% knowledgeCheck %}
question: "Which file is the source of truth for a module's lesson content?"
options:
  - text: "lesson.md"
    correct: true
    feedback: "Correct - each module's lesson.md is the authored source the build renders."
  - text: "index.html"
    correct: false
    feedback: "index.html is generated output, not the authored source."
  - text: "imsmanifest.xml"
    correct: false
    feedback: "The manifest describes the package to the LMS; it carries no lesson prose."
{% endknowledgeCheck %}

## Page Boundaries

Every `##` heading starts a new page. Keeping pages short helps learners
and keeps the dwell-time gating predictable.

{% knowledgeCheck %}
question: "What does a `##` heading mark in a lesson.md file?"
options:
  - text: "A speaker note"
    correct: false
    feedback: "Speaker notes live in source decks, not lesson markdown."
  - text: "A page boundary"
    correct: true
    feedback: "Correct - the build splits the lesson into pages at every ## heading."
  - text: "A knowledge check"
    correct: false
    feedback: "Knowledge checks use the knowledgeCheck shortcode, not headings."
  - text: "An image placement"
    correct: false
    feedback: "Images are placed with standard markdown image syntax."
{% endknowledgeCheck %}

## Wrap-up

You now know how the pipeline turns markdown into a SCORM package.
