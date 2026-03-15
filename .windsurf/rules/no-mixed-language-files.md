---
trigger: always_on
---

## No Mixed Language Files

Do not embed more than a trivial amount of (less than 10 lines) of an auxiliary language into a file of a different language.

Non-exhaustive examples:

 - Do not embed > 10 lines of JavaScript into an HTML file
 - Do not embed > 10 lines of CSS into an HTML file
 - Do not embed > 10 lines of HTML in Python file

 If the content to be "embedded" has any dynamic elements, it should use an appropriate
 templating language and rendering engine for the host framework.

 It is aceptable, however, to ebmed SQL in Python file


