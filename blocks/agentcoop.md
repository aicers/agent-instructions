<!-- BEGIN shared:agentcoop -->
## AgentCoop

AgentCoop is the pipeline this organization runs over its GitHub issues,
so its vocabulary turns up in issue bodies and pull request comments
here — and an agent working in this repository may itself be running
inside it.

- Two agents do the work. The **author** (Agent A) produces, the
  **reviewer** (Agent B) reviews independently, and the two converge
  through structured feedback; a deadlock escalates to a human rather
  than resolving silently. They are usually different models.
- **Implementation** turns one issue into a pull request with green CI.
  The author implements it in a dedicated worktree, self-checks, opens
  the pull request, and drives CI to green; the reviewer then reviews
  the pushed branch and the two iterate in the pull request's comment
  thread, tagged `[Author Round N]` and `[Reviewer Round N]`, until it
  is approved.
- **Design** shapes work into issues: an RFC file becomes an umbrella
  issue over a sub-issue tree, or a single issue is refined — and split
  only when one pull request cannot cover it.
- **Verification** holds a completed issue against the diffs that closed
  it and files follow-up sub-issues for whatever it did not deliver.
- The issue is the contract, and the only input a run is given. A human
  writes that seed and merges the result; AgentCoop invents no
  requirement and asks no clarifying question along the way.
<!-- END shared:agentcoop -->
