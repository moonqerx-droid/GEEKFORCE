"""Quality gate: the golden dialogues must not get worse.

Full report: `python -m app.eval_dialogues`. Raise the thresholds as the numbers improve.
"""

from app.eval_dialogues import run, summary


def test_golden_dialogues_meet_the_quality_bar():
    results = run()
    table = summary(results)
    # «контроль-4» is a deliberately hard holdout written before the answers-v2 changes;
    # it has its own floor below and does not dilute the overall bar.
    core = summary([r for r in results if "контроль-4" not in r.tags])
    failures = "\n".join(f"{r.id}: {'; '.join(r.problems)}" for r in results if not r.ok)

    # Dialogue behaviour is fully under our control: every golden dialogue must be clean.
    assert table["диалог"]["clean"] == 1.0, failures
    # Understanding of free wording on keywords, lemmas and typo correction alone (CI has
    # no Ollama). With meaning-based matching (`--semantic`) the same set scores ~97%.
    assert table["понимание"]["playbook"] >= 0.85, failures
    assert core["всего"]["clean"] >= 0.87, failures
    assert core["всего"]["questions"] <= 1.5, failures
    assert table["контроль-4"]["playbook"] >= 0.88, failures
