"""Score the verification gate against the human-labelled sample (method: specs/guardrails/).

Positive means *bad*: the gate's job is to stop bad items and hints. For the generated records,
which sample the live pipeline before the gate:

  raw bad rate        bad / all                    how often the generator is wrong
  served error rate   bad / served                 what learners see (the headline number)
  false alarm rate    good rejected / good         good content thrown away (cost, not safety)
  catch rate          in-scope bad rejected / in-scope bad

Planted records (defects put in on purpose, known by construction) measure the catch rate on its
own: a random sample holds too few naturally bad items to say anything about the gate. Defects the
gate was never built to catch (a leaked answer, bad Vietnamese) are counted and reported, never
charged to it.

Every rate carries its interval and its n, and the report says what the sample cannot show.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.evalkit.labels import Kind, Record, classify
from app.evalkit.stats import Rate, cohen_kappa, rate

Verdict = Literal["served", "rejected"]  # verified and shown / needs_review and withheld

MIN_PLANTED = 36  # all caught is needed to show a 90% catch rate at 95% confidence
SERVED_FOR_5_PERCENT = 73  # served with none bad, to show an error rate under 5%
MIN_KAPPA = 0.6  # below this, the labelers do not share a definition yet
MIN_NATURAL_BAD = 10


@dataclass(frozen=True)
class KindReport:
    kind: Kind
    generated: int
    planted: int
    raw_bad: Rate
    served: int
    rejected: int
    served_error: Rate  # any defect among what was served
    served_in_scope_error: Rate  # only the defects the gate should catch
    false_alarm: Rate
    catch_generated: Rate
    catch_planted: Rate
    out_of_scope_served: int  # served with only defects outside the gate's scope
    leaks_served: int  # hints: served hints labelled as leaking the answer (0 for items)
    kappa: float | None
    kappa_n: int
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        def r(x: Rate) -> dict[str, Any]:
            return {"k": x.k, "n": x.n, "point": x.point, "low": x.low, "high": x.high}

        return {
            "kind": self.kind,
            "generated": self.generated,
            "planted": self.planted,
            "served": self.served,
            "rejected": self.rejected,
            "raw_bad": r(self.raw_bad),
            "served_error": r(self.served_error),
            "served_in_scope_error": r(self.served_in_scope_error),
            "false_alarm": r(self.false_alarm),
            "catch_generated": r(self.catch_generated),
            "catch_planted": r(self.catch_planted),
            "out_of_scope_served": self.out_of_scope_served,
            "leaks_served": self.leaks_served,
            "kappa": self.kappa,
            "kappa_n": self.kappa_n,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class GuardrailReport:
    items: KindReport | None
    hints: KindReport | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items.to_dict() if self.items else None,
            "hints": self.hints.to_dict() if self.hints else None,
        }

    def format(self) -> str:
        parts = [_format_kind(k) for k in (self.items, self.hints) if k is not None]
        return "\n\n".join(parts)


def score(records: Sequence[Record], verdicts: Mapping[str, Verdict]) -> GuardrailReport:
    """Score the gate. `verdicts` maps every record id to what the gate did with it."""
    ids = {r.id for r in records}
    missing, extra = sorted(ids - verdicts.keys()), sorted(verdicts.keys() - ids)
    if missing or extra:
        raise ValueError(f"verdicts do not match records (missing {missing}, unknown {extra})")
    return GuardrailReport(
        _score_kind([r for r in records if r.kind == "item"], verdicts, "item"),
        _score_kind([r for r in records if r.kind == "hint"], verdicts, "hint"),
    )


def _score_kind(
    records: Sequence[Record], verdicts: Mapping[str, Verdict], kind: Kind
) -> KindReport | None:
    if not records:
        return None
    gen = [r for r in records if r.source == "generated"]
    planted = [r for r in records if r.source == "planted"]
    served = [r for r in gen if verdicts[r.id] == "served"]
    rejected = [r for r in gen if verdicts[r.id] == "rejected"]

    good = [r for r in gen if r.klass == "good"]
    in_scope = [r for r in gen if r.klass == "in_scope"]
    bad = [r for r in gen if r.klass != "good"]

    # Class agreement of the first two labelers, on the records that were double-labelled.
    pairs = [(r.labels[0], r.labels[1]) for r in gen if len(r.labels) >= 2]
    kappa_n = len(pairs)
    kappa = cohen_kappa(
        [classify(kind, a.defects) for a, _ in pairs],
        [classify(kind, b.defects) for _, b in pairs],
    )

    report = KindReport(
        kind=kind,
        generated=len(gen),
        planted=len(planted),
        raw_bad=rate(len(bad), len(gen)),
        served=len(served),
        rejected=len(rejected),
        served_error=rate(sum(r.klass != "good" for r in served), len(served)),
        served_in_scope_error=rate(sum(r.klass == "in_scope" for r in served), len(served)),
        false_alarm=rate(sum(verdicts[r.id] == "rejected" for r in good), len(good)),
        catch_generated=rate(sum(verdicts[r.id] == "rejected" for r in in_scope), len(in_scope)),
        catch_planted=rate(sum(verdicts[r.id] == "rejected" for r in planted), len(planted)),
        out_of_scope_served=sum(r.klass == "out_of_scope" for r in served),
        leaks_served=sum("leaks_answer" in r.final_defects for r in served),
        kappa=kappa,
        kappa_n=kappa_n,
        notes=(),
    )
    return KindReport(**{**report.__dict__, "notes": tuple(_notes(report))})


def _notes(r: KindReport) -> list[str]:
    """What this sample cannot show; printed under the numbers so nobody over-reads them."""
    notes = []
    if r.planted < MIN_PLANTED:
        notes.append(
            f"only {r.planted} planted {r.kind}s: even with every one caught, a 90% catch rate "
            f"cannot be shown (needs {MIN_PLANTED})"
        )
    natural_bad = r.catch_generated.n
    if natural_bad < MIN_NATURAL_BAD:
        notes.append(
            f"only {natural_bad} naturally bad {r.kind}s in the sample: the catch rate on generated"
            " "
            "content says little, rely on the planted ones"
        )
    high = r.served_error.high
    if high is not None and high > 0.05:
        notes.append(
            f"served error rate: the data cannot rule out more than 5% (upper bound {high:.0%}); "
            f"showing under 5% needs {SERVED_FOR_5_PERCENT}+ served with none bad"
        )
    if r.kappa_n < 5:
        notes.append("fewer than 5 double-labelled records: labeler agreement is not measured")
    elif r.kappa is None:
        notes.append("labelers always gave the same class: agreement beyond chance is undefined")
    elif r.kappa < MIN_KAPPA:
        notes.append(
            f"labelers agree only weakly (kappa {r.kappa:.2f} < {MIN_KAPPA}): align the "
            "definitions "
            "and relabel before trusting these numbers"
        )
    if r.leaks_served:
        notes.append(f"{r.leaks_served} served hint(s) leak the answer: a tutor rule was broken")
    if r.out_of_scope_served:
        notes.append(
            f"{r.out_of_scope_served} served {r.kind}(s) have only defects the gate is not "
            "built to "
            "catch (listed, not charged to the gate)"
        )
    return notes


def _format_kind(r: KindReport) -> str:
    title = "Items" if r.kind == "item" else "Tutor hints"
    lines = [
        f"{title}: {r.generated} generated ({r.served} served, {r.rejected} withheld),"
        f" {r.planted} planted",
        f"  generator wrong before the gate   {r.raw_bad}",
        f"  served error rate (any defect)    {r.served_error}",
        f"  served error, gate-scope defects  {r.served_in_scope_error}",
        f"  false alarms (good withheld)      {r.false_alarm}",
        f"  catch rate, generated             {r.catch_generated}",
        f"  catch rate, planted               {r.catch_planted}",
    ]
    if r.kind == "hint":
        lines.append(f"  served hints that leak the answer {r.leaks_served}")
    if r.notes:
        lines += ["  Read with care:", *[f"   - {n}" for n in r.notes]]
    return "\n".join(lines)
