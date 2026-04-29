---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code
source: obra/superpowers (skills/test-driven-development/SKILL.md)
---

# Test-Driven Development (TDD)

## Overview

Write the test first. Watch it fail. Write minimal code to pass.

**Core principle:** If you didn't watch the test fail, you don't know if it tests the right thing.

**Violating the letter of the rules is violating the spirit of the rules.**

## When to Use

**Always:**
- New features
- Bug fixes
- Refactoring
- Behavior changes

**Exceptions (ask your human partner):**
- Throwaway prototypes
- Generated code
- Configuration files

Thinking "skip TDD just this once"? Stop. That's rationalization.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over.

## Red-Green-Refactor

- **RED**: Write one minimal failing test showing the behavior.
- **Verify RED**: Watch it fail for the right reason (mandatory).
- **GREEN**: Write the simplest code to pass.
- **Verify GREEN**: Watch it pass, ensure others pass too (mandatory).
- **REFACTOR**: Clean up without changing behavior, keep tests green.

## Good Tests (high signal)

- One behavior per test
- Clear behavior-focused name
- Minimal setup
- Prefer testing real behavior over mock behavior

