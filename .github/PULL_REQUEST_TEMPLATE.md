## Linked issue

Closes #N

The linked issue must carry the `status:approved` label. Valid keywords: `Closes`, `Fixes`, `Resolves` (for example `Fixes #42`).

## Type

Check exactly one and add the matching label to the pull request:

- [ ] Bug fix (`type:bug`)
- [ ] New feature (`type:feature`)
- [ ] Documentation only (`type:docs`)
- [ ] Code refactoring (`type:refactor`)
- [ ] Maintenance/tooling (`type:chore`)
- [ ] Breaking change (`type:breaking-change`)

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
- [ ] Exactly one type label (`type:bug`, `type:feature`, `type:docs`, `type:refactor`, `type:chore`, or `type:breaking-change`)
- [ ] `python3 tools/test.py` passes
- [ ] Conventional Commits (`type(scope): description`)
- [ ] No `Co-Authored-By` trailers
- [ ] Changed lines are at most 400, or maintainer-approved `size:exception` applies
- [ ] Docs updated if behavior changed
