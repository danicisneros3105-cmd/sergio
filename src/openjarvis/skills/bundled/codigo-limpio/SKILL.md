---
name: codigo-limpio
description: Write, fix and review code that works the first time. Use for any programming task.
license: Apache-2.0
metadata:
  openjarvis:
    user_invocable: false
---

# Código limpio

- Read the error and the surrounding code before changing anything; reproduce the bug first.
- The smallest change that fixes it, in the style of the file around it.
- Every fix with a test that failed before and passes after.
- Names that say what things are; no comments that repeat the code; comments for the why.
- Never hide an error: handle it or let it surface with a clear message.
- Run the linter and the tests before saying it works; say which ones ran.
