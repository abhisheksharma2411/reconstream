"""E9 -- the worked timeline, computed from the contract it illustrates.

Section~III walks one movement tick by tick: a capture settles, the ledger
publishes, a batch boundary passes, a bound expires, and a reconciler raises a
break too early. Every instant in that paragraph is arithmetic over the
declared source model -- the ledger's two-tick lag, the bank's seventy-five
tick bound, the sixty-tick batch cycle -- and every one was typed in.

The second half of the paragraph is the point the paper is making: a timeout
measured from publication rather than from the movement fires at different
instants for the same bank and the same bound, and the gap between them is the
ledger's own lateness. That gap was typed in too.

So compute them all, from ``SourceModel`` and ``decidable_at``. If a bound
changes, the timeline changes with it instead of quietly disagreeing.
"""

from __future__ import annotations

from _common import write

from reconstream._p1 import ensure_p1
from reconstream.contract import BANK_SRC, LEDGER_SRC, SourceModel

ensure_p1()
from finalitybench.faults import (  # noqa: E402
    BANK_BATCH, BANK_LAG, _bank_visible_at as bank_visible_at)

#: The instants the paragraph starts from. Everything else is derived.
SETTLES_AT = 1000
#: A timeout a reconciler might set, measured from whenever it heard.
TIMEOUT = 80
#: How late the ledger is in the second half of the paragraph.
LATE_PUBLICATION = 1200


def main() -> None:
    model = SourceModel()
    ledger_lag = model.lateness(LEDGER_SRC)
    bank_bound = model.lateness(BANK_SRC)

    published = SETTLES_AT + ledger_lag
    # What the contract knows without knowing where in the cycle the movement
    # fell: the credit can be as prompt as the lag and as late as one tick
    # short of a full further cycle. That range, not the actual posting
    # instant, is what a reconciler may assume.
    delays = [bank_visible_at(t) - t for t in range(0, BANK_BATCH)]
    window_opens = SETTLES_AT + min(delays)
    window_closes = SETTLES_AT + max(delays)
    # What this movement actually does, which the contract does not get to use.
    actual_post = bank_visible_at(SETTLES_AT)
    decidable = model.decidable_at(SETTLES_AT, BANK_SRC)

    prompt_timeout = published + TIMEOUT
    late_timeout = LATE_PUBLICATION + TIMEOUT

    write("e9_worked_instance.json", {
        "config": {"settles_at": SETTLES_AT, "batch_cycle": BANK_BATCH, "bank_lag": BANK_LAG,
                   "timeout": TIMEOUT, "late_publication": LATE_PUBLICATION,
                   "model": model.as_dict()},
        "timeline": {
            "settles_at": SETTLES_AT,
            "ledger_publishes_at": published,
            "earliest_credit": window_opens,
            "latest_credit": window_closes,
            "actual_posting_instant": actual_post,
            "actual_delay": actual_post - SETTLES_AT,
            "decidable_at": decidable,
        },
        "timeouts": {
            "prompt_publication_fires_at": prompt_timeout,
            "late_publication_fires_at": late_timeout,
            "late_timeout_after_decidable": late_timeout - decidable,
            "gap_between_the_two": late_timeout - prompt_timeout,
        },
        "headline": {
            "ledger_lag": ledger_lag,
            "bank_bound": bank_bound,
            "decidable_at": decidable,
            "bank_batch": BANK_BATCH,
            "bank_lag": BANK_LAG,
            "earliest_credit": window_opens,
            "latest_credit": window_closes,
            "actual_posting_instant": actual_post,
            # A break raised here is unsound: the declared bound has not
            # expired, so a continuation exists in which the credit still
            # posts -- whatever this particular movement happens to do.
            "an_early_break_at": decidable - 15,
            "a_later_credit_at": decidable - 5,
            "prompt_publication_fires_at": prompt_timeout,
            "late_publication_fires_at": late_timeout,
            "late_timeout_after_decidable": late_timeout - decidable,
            "gap_between_the_two": late_timeout - prompt_timeout,
        },
    })


if __name__ == "__main__":
    main()
