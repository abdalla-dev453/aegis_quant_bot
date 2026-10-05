---
name: GitHub publishing from Replit
description: Authenticated GitHub publishing and byte-accurate tree verification from a Replit workspace.
---

When `git push` fails because the workspace has no Git credentials, use the attached GitHub connector for authenticated Git database API writes. In GitHub's tree API, send text file contents as UTF-8; for binary files, create a blob with Base64 encoding and place its SHA in the tree entry.

**Why:** GitHub can accept a tree that stores Base64 text as literal file contents, so a successful API response does not prove the pushed snapshot is correct.

**How to apply:** Compare the resulting GitHub commit's tree SHA with local `HEAD^{tree}`. Fetch and synchronize the local branch only after the tree hashes match.
