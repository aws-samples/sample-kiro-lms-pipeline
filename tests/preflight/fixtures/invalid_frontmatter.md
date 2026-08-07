---
module_id: module-broken
title: "This YAML is broken
  - missing closing quote
  duration_minutes: [invalid
  nested:
    key: value
    another: : : bad
---

# This lesson has broken frontmatter

The YAML above is syntactically invalid due to an unclosed string and malformed list.

{% nextPage %}

## Content

Some content here that would be valid if the frontmatter were correct.

{% moduleEnd %}
