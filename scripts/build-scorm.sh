#!/usr/bin/env bash
# Build a SCORM 1.2 zip for any course in this repo.
#
# Usage:
#   scripts/build-scorm.sh [course-short-name]
#
# Default course is "sample-course". All courses live at ./courses/<name>/
# and have their own course.yaml + build/ tree.
#
# The zip destination comes from ``course.scorm.output`` in the course's
# course.yaml, resolved relative to the course root.

set -euo pipefail

COURSE="${1:-sample-course}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COURSE_ROOT="$REPO_ROOT/courses/$COURSE"

COURSE_YAML="$COURSE_ROOT/course.yaml"
if [ ! -f "$COURSE_YAML" ]; then
  echo "Error: course.yaml not found at $COURSE_YAML" >&2
  exit 1
fi

echo "Building SCORM for '$COURSE'..."
echo "  COURSE_ROOT=$COURSE_ROOT"

# Clean intermediate eleventy output so nothing from a previous course leaks.
rm -rf "$REPO_ROOT/scorm/build"

# Run the Eleventy build.
COURSE_ROOT="$COURSE_ROOT" npm --prefix "$REPO_ROOT/scorm/src" run build

# Read the zip destination from course.yaml (relative to the course root).
ZIP_REL=$(
  python3 -c \
    "import yaml, sys; print(yaml.safe_load(open(sys.argv[1]))['scorm']['output'])" \
    "$COURSE_YAML"
)
ZIP_ABS="$COURSE_ROOT/$ZIP_REL"

mkdir -p "$(dirname "$ZIP_ABS")"
rm -f "$ZIP_ABS"

# Zip from inside scorm/build so paths are zip-root relative.
(cd "$REPO_ROOT/scorm/build" && zip -qr "$ZIP_ABS" .)

echo "Done: $ZIP_ABS"
