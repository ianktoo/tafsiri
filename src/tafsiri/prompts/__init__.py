"""Centralized, importable prompts.

All prompt text lives here (not inline in evaluators) so it's easy to find,
override, and reuse. Import what you need:

    from tafsiri.prompts import JUDGE_SYSTEM, build_judge_user

Pass a custom ``system_prompt`` / ``user_builder`` to an evaluator to override.
"""

from tafsiri.prompts.judge import JUDGE_SYSTEM, build_judge_user

__all__ = ["JUDGE_SYSTEM", "build_judge_user"]
