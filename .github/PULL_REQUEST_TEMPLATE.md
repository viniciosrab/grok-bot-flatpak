## Linked issue

Closes #N

The linked issue must carry the `status:approved` label. Valid keywords: `Closes`, `Fixes`, `Resolves` (for example `Fixes #42`).

## Type

Check exactly one and add the matching label to the pull request:

- [ ] Bug fix (`type:bug`)
- [ ] Maintenance/tooling (`type:chore`)

## Summary

- What this PR does and why it matters.

## Changes

| File | Change |
|------|--------|
| `path/to/file` | What changed |

## Test plan

- [ ] `python3 tools/test.py` passes (workspace gate, required)
- [ ] Runtime evidence: <command and result, or `N/A` with reason>

## Rollback

<Which files/behavior can be reverted without touching unrelated work.>

## Checklist

- [ ] Linked issue has `status:approved`
- [ ] Exactly one type label (`type:bug` or `type:chore`)
- [ ] `python3 tools/test.py` passes
- [ ] Conventional Commits (`type(scope): description`)
- [ ] Changed lines are at most 400, or maintainer-approved `size:exception` applies
- [ ] Docs updated if behavior changed
