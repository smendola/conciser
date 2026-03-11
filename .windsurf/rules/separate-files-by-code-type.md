---
trigger: always_on
---

Do not embed more than a few lines of any programming or data language into a
file of a different programming language.

Examples

- No large chunks of HTML in Python files
- No large chunks of JavaScript in HTML files
- No large chunks of CSS in HTML files

Instead, load the "auxiliary" code from a dedicated file with the appropriate
extension (e.g., .html, .js, .css) Use an appropriate templating
language/processor if the auxiliary code must contain dynamic content.

It's acceptable to embed even substantial SQL queries in Python files, however.
