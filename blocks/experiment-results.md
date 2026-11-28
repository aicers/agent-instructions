<!-- BEGIN shared:experiment-results -->
## Experiment results

Result files include experiment and measurement output such as JSON,
logs, and captures. The repository's own sections below name the
repository whose discussions hold evidence files.

- **Report first.** If the report can explain the result without the
  file, put no file anywhere. Write the conclusion, the numbers it rests
  on, and how to get them again: the commit built, tool versions,
  parameters, hosts, and procedure.
- **Never commit a result file to any repository**, even on a pull
  request branch that deletes it before the merge. A squash merge keeps
  it out of the default branch, but the pull request's ref keeps it on
  the hosting service permanently.
- **Evidence goes to a discussion.** When a file must be shown as
  evidence, post it in a discussion of the repository named in this
  repository's own sections. Reference the discussion from the issue or
  pull request by its full URL, never as `#N`: discussions share the
  issue and pull request number namespace.
- **How to post.** Use one discussion per experiment. Its body lists the
  issues and pull requests, in any repository, that the files serve, the
  source commit, and whether the result can be reproduced; if not, say
  why. Post each file as its own comment through the GraphQL API
  (`addDiscussionComment`). Start with a header line giving the file
  name and SHA-256 of the whole original file, followed by its content
  in a fenced code block. Base64-encode a binary file. If the comment
  would exceed the 65,536-character body limit, including the header and
  fences, split the content into numbered comments within that limit.
  The reader reassembles the file, decoding base64 for a binary file,
  and checks it against the SHA-256. A session with a signed-in browser
  may instead attach the file through the web interface, up to 25 MB.
  Do not post a file over 25 MB; the report gives its location in an
  existing archive and its hash.
- **Delete when the work is over.** When every issue the discussion
  lists is closed and every pull request it lists is merged or closed,
  delete the discussion (`deleteDiscussion`). A discussion whose body
  says its result cannot be reproduced may be kept; the report that
  cites it says it is kept.
- **Local copies expire.** Delete result files kept on a machine, a lab
  server, or a runner 50 days after they last changed. Notes, scripts,
  and progress logs are not result files and are not covered.
- **Never post secrets or customer data**, in a discussion or anywhere
  else this block covers.
<!-- END shared:experiment-results -->
