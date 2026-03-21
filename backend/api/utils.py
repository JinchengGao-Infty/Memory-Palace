import difflib
from typing import Tuple

try:
    from diff_match_patch import diff_match_patch as DiffMatchPatch
except ModuleNotFoundError:
    DiffMatchPatch = None


def get_text_diff(text_a: str, text_b: str) -> Tuple[str, str, str]:
    """
    Compare two text blobs and return their diff artifacts.

    Args:
        text_a: Original text.
        text_b: Updated text.

    Returns:
        (diff_html, diff_unified, summary)
        - diff_html: HTML diff suitable for UI rendering.
        - diff_unified: Unified diff text.
        - summary: Short change summary.
    """
    diff_unified = _build_unified_diff(text_a, text_b)

    if DiffMatchPatch is None:
        diff_html = _build_fallback_diff_html(text_a, text_b)
        summary = _generate_fallback_diff_summary(text_a, text_b)
        return diff_html, diff_unified, summary

    dmp = DiffMatchPatch()
    diffs = dmp.diff_main(text_a, text_b)
    dmp.diff_cleanupSemantic(diffs)
    diff_html = dmp.diff_prettyHtml(diffs)
    summary = _generate_diff_summary(diffs, text_a, text_b)

    return diff_html, diff_unified, summary


def _build_unified_diff(text_a: str, text_b: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            text_a.splitlines(keepends=True),
            text_b.splitlines(keepends=True),
            fromfile="old_version",
            tofile="new_version",
            lineterm=""
        )
    )


def _build_fallback_diff_html(text_a: str, text_b: str) -> str:
    html_diff = difflib.HtmlDiff(wrapcolumn=80)
    return html_diff.make_table(
        text_a.splitlines(),
        text_b.splitlines(),
        fromdesc="old_version",
        todesc="new_version",
        context=True,
        numlines=2,
    )


def _generate_fallback_diff_summary(text_a: str, text_b: str) -> str:
    additions = 0
    deletions = 0

    for tag, start_a, end_a, start_b, end_b in difflib.SequenceMatcher(
        a=text_a,
        b=text_b,
    ).get_opcodes():
        if tag == "insert":
            additions += end_b - start_b
        elif tag == "delete":
            deletions += end_a - start_a
        elif tag == "replace":
            deletions += end_a - start_a
            additions += end_b - start_b

    return _format_diff_summary(additions, deletions, len(text_a), len(text_b))


def _generate_diff_summary(diffs, text_a: str, text_b: str) -> str:
    """Generate a compact summary for the semantic diff."""
    additions = 0
    deletions = 0

    for op, text in diffs:
        length = len(text)
        if op == DiffMatchPatch.DIFF_INSERT:
            additions += length
        elif op == DiffMatchPatch.DIFF_DELETE:
            deletions += length
    return _format_diff_summary(additions, deletions, len(text_a), len(text_b))


def _format_diff_summary(
    additions: int,
    deletions: int,
    total_old: int,
    total_new: int,
) -> str:
    if total_old == 0:
        return f"Added content: {total_new} chars"

    if total_new == 0:
        return f"Deleted all content: {total_old} chars removed"

    change_ratio = (additions + deletions) / (total_old + total_new) * 100

    if change_ratio < 5:
        return f"Small change: +{additions} chars, -{deletions} chars"
    elif change_ratio < 20:
        return f"Moderate change: +{additions} chars, -{deletions} chars"
    else:
        return (
            f"Large change: +{additions} chars, -{deletions} chars, "
            f"change ratio {change_ratio:.1f}%"
        )
