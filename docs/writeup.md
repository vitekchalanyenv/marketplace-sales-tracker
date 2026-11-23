# Letting an LLM comment on money without letting it make up numbers

*A one-page write-up of the weekly commentary in [marketplace-sales-tracker](../README.md).*

## The problem

Every Monday my sales e-mail gets a short comment on the past week: what changed, what sold. That is a good job for
an LLM. Two or three sentences that pick out what matters read better than a table. It is also the one place where
a wrong number does real damage. A comment that says income *rose* when it fell, or credits one marketplace with
another one's money, looks just as confident as a correct one. And I would read it at 8 a.m. without checking.

So the requirement was simple to state: **Claude may write the words, never the facts.**

## First attempt, and why it failed

The first version let Claude write numbers and then checked that **every number in the text exists somewhere in the
data**. It had tests, an eval set and a README section. It looked thorough.

An independent review broke it in minutes:

- *"Sales rose 19 %"* when they fell 19 %. 19 is in the data, so the check passed.
- The unit counts of two marketplaces swapped. Both numbers exist, so it passed.
- One marketplace's income attributed to another. Same thing.

The check verified that a number *existed*, not that it was *attached to the right thing*. Worse, the README claimed
the eval covered "swapped amounts", but that test case used a number that was not in the data at all. So it tested
something easier than it claimed. That one went into the [log of mistakes](AI_CHYBY.md).

## The redesign: take the numbers away

Now Claude never sees a value it could misplace:

1. **Code computes everything** for the week: income and units per marketplace and product, in USD and CZK, and the
   comparison with the week before. It turns each of these into a named placeholder with a meaning, for example
   `{cosmos_kc}` = income from Cosmos in CZK.
2. **Direction and ranking are values too.** `{smer_prijmu}` holds "rose", "fell" or "stayed the same", decided by
   code. `{nejlepsi_marketplace}` is the channel with the highest income. Claude cannot get "rose" wrong, because
   it never decides it.
3. **Claude writes 2–3 sentences with placeholders only.**
4. **A deterministic check** rejects the text if it contains:
   - a digit or a number word,
   - its own direction or quantity words ("most", "both", "only"),
   - its own superlative or a cause ("because of"),
   - a product name written out instead of its placeholder,
   - an unknown placeholder,
   - a value placed next to the wrong name. The nearest marketplace or product name *before* a placeholder in the
     same sentence must be the one the value belongs to.
5. **Code fills in the values.** If the text fails, Claude gets one retry with the problems listed. If that fails
   too, the e-mail goes out with the code's numbers only, and the rejected text goes to the log.

The design principle: **the LLM chooses what to say, code owns every fact it refers to.**

## Three rounds of review

Each round of independent review found a different kind of hole:

1. **Facts:** the "exists somewhere" check above. Fixed with placeholders and the attribution rule.
2. **Facts in words:** "Gumroad had the only sale, Cosmos both of the others", "mostly on Gumroad", "the strongest
   channel", "fell mainly because of Gumroad". None of them contains a digit, and all of them are claims. Quantifiers,
   superlatives and causes went on the lists. Every attack became a test case.
3. **Too strict:** the stricter check now rejected *"Most of the income came from {nejlepsi_marketplace}"*. That is
   the most natural use of the ranking placeholder I had built for it. A safety check that blocks the feature is not
   safe, it is just off. A positive superlative is now allowed in the same sentence as a ranking placeholder.

The eval set has 11 good and 27 bad hand-written comments, and it runs in CI without network access.

## Measuring instead of claiming

After the third round I stopped arguing about whether the check was "too strict" and measured it: 20 runs of
`claude-opus-5-5` on the demo week, for each prompt version.

| Prompt | Passed 1st try | After retry | Gave up | Value placeholders per comment | Sentences | Czech agreement risk |
|---|---|---|---|---|---|---|
| v1: "write 2–4 sentences" | 20 | 0 | 0 | 12.8 | 4 | 17 of 20 |
| v2: "pick one or two things, don't repeat the overview below" | 20 | 0 | 0 | 0.9 | 2 | 0 of 20 |

The check never starved the feature. What the eval exposed was something I had not been looking for. Claude restated
almost every number that was already in the table below the comment. It also kept writing "se prodalo {celkem_kusu}",
which breaks Czech grammar once the code fills in "4 kusy". Prompt v2 fixed both, and the eval shows it. Caveat:
it is one week of made-up data, so there is little variety.

## What it does not catch

The check is a filter made of word lists and one positional rule. It does not understand meaning. Order and quantity
hidden in a verb still pass: *"Gumroad dominated"*, *"a record week"*. The first live Monday comment used a few
words of that kind. They happened to be true, but nothing verified them. Three things keep this acceptable:

- the numbers in the e-mail are always the code's;
- the comment is labelled as Claude's;
- the README states these limits next to the claims.

## Why not a second LLM as a judge?

It would be non-deterministic and cost another call, and it could hallucinate in turn. For two or three sentences,
a deterministic check with clearly stated limits is the better trade-off. It either passes or names exactly what
failed, the same way every time, and it can be tested in CI.

## Takeaways

- **Give the model choices, not facts.** Anything code can compute, including the direction of a change and a
  ranking, should be a value the model can only refer to.
- **Attack your own guardrail before trusting it.** Each review round found a hole the tests did not cover. Every
  hole became a test.
- **A guardrail that blocks the feature has failed too.** Measure pass rates on the real model, not only rejections
  on a hand-made set.
- **Write down the limits.** The check is honest about what it cannot see, so the e-mail is designed around that.

*The code was written by an AI coding agent (Claude Code) under my review. The mistakes that were caught, including
the first version of this check, are logged in [`docs/AI_CHYBY.md`](AI_CHYBY.md) (Czech).*
