---
trigger: always_on
---

When renaming or moving files, always use `git mv` to maintain git history.
When adding new files that are meant to be tracked by git, always use `git add` to add them to the staging area.
When removing files, always use `git rm` to remove them from the repository.

Do not git add temp work files used for debugging or one-time operations.
