# A practical guide to translation evals

A from-scratch guide to **evaluating machine translation** — what the signals
mean, how to combine them, how to read the results, and where they mislead.
Written around `tafsiri`, but the ideas are general.

---

## 1. Why evaluate at all?

A translation system gives you an answer for every input. The hard question is:
**can you trust it?** A fluent-sounding translation that quietly changes the
meaning is *more* dangerous than an obvious garble, because nobody double-checks
it. In safety-critical settings (medical, emergency, legal, financial) that gap
can cause real harm.

This matters most for **low-resource languages** — many African languages
included — where training data is scarce and quality is uneven. You cannot
assume "the model is good"; you have to **measure**, per language and per kind of
text.

So evaluation answers a specific question:

> *How good is this model, for **this** language, on **this** kind of text — and
> how confident am I in that judgment?*

---

## 2. Two families of evaluation

**Reference-based** — compare the output against a human "gold" translation.
Metrics: BLEU, chrF, METEOR, COMET. Accurate, but they need a reference
translation for every sentence, which is expensive and often unavailable for
low-resource languages.

**Reference-free (quality estimation)** — judge a translation *without* a gold
answer, using signals you can compute from the translation itself (and the
source). Cheaper, scales to any language, and is what you need when you have no
references.

`tafsiri` is **reference-free**. It combines three independent signals.

---

## 3. The three signals

Each evaluator returns one score in **0..1** (higher = better), or `None` when it
can't judge an item. They are deliberately independent — they fail in different
ways, so agreement between them is meaningful.

### 3.1 Confidence (the model's self-report)

The engine returns its own confidence (Babel does this). **Cheap** — no extra
calls — but it's a *self-assessment*. Models are often **overconfident**,
especially on languages they're weak at. Treat it as a weak prior, not proof.

> In our Amharic run, confidence averaged **0.87** while the independent signals
> sat at **0.67–0.73** — a textbook overconfidence gap.

### 3.2 Back-translation (round-trip)

Translate the output **back** into the source language, then measure how close
the round-trip lands to the original.

```
English  →[engine]→  Swahili  →[engine]→  English'
                                   compare(English, English')
```

If meaning was lost, the round-trip drifts and the similarity drops. `tafsiri`
measures similarity with a token-sequence ratio (stdlib `difflib`).

**Strengths:** reference-free, language-agnostic, catches dropped/added meaning.
**Caveats:**
- It scores a *round trip*, so it blames the source→target and target→source
  steps together — a perfect back-translation can still hide a flaw the reverse
  step happened to "fix."
- Surface similarity ≠ meaning. Paraphrases score lower than they deserve;
  fluent mistranslations can score higher than they deserve.
- It costs one extra API call per item (doubles your call volume).

### 3.3 LLM-as-judge

Ask a separate, capable LLM to rate the translation on two axes, 1–5:
- **adequacy** — is the full meaning preserved (nothing added or lost)?
- **fluency** — is it natural, grammatical text in the target language?

`tafsiri` normalizes the mean of the two to 0..1. The judge is provider-agnostic
(Claude / OpenAI / Gemini / local Ollama).

**Strengths:** closest to human judgment; can explain *why*; catches subtle
meaning errors surface metrics miss.
**Caveats:**
- It's only as good as the judge model — and judges can be weak on the very
  low-resource languages you're testing (the same blind spot as the translator).
- Known biases: length bias, self-preference (a model rating its own family),
  leniency. Use a *different, strong* model as judge where you can.
- Costs an LLM call per item.

---

## 4. Combining the signals

A weighted mean over whichever signals produced a score (missing signals are
skipped and their weight is redistributed):

```
aggregate = Σ(weightᵢ · scoreᵢ) / Σ(weightᵢ)      # over non-None signals
```

Default weights lean on the signals that test *meaning* hardest:

| signal | weight | rationale |
| ------ | ------ | --------- |
| `confidence` | 1.0 | weak prior — it's a self-report |
| `back_translation` | 1.5 | independent evidence of preserved meaning |
| `llm_judge` | 2.0 | closest proxy to human judgment |

Weights are configurable (`scoring.Scorer`). There's no universally "correct"
set — calibrate them against human ratings for your domain if you can.

---

## 5. Ratings & thresholds

The aggregate is bucketed into a rating:

| rating | default cutoff | meaning |
| ------ | -------------- | ------- |
| `good` | ≥ 0.85 | trustworthy enough to use / keep as-is |
| `marginal` | ≥ 0.70 | usable, but flag for human review |
| `risky` | < 0.70 | do not rely on |
| `no_score` | — | translation failed or nothing could be scored |

The bar is **deliberately high for safety-critical text** — when a wrong
translation can cost a life, "probably fine" isn't good enough. Lower the
thresholds (`--good`, `--marginal`) for casual content where mistakes are cheap.

This is also why training-data export filters by rating (`--min-rating`): you
don't want low-quality pairs poisoning a fine-tune.

---

## 6. Reading the report

A report has totals, a verdict, and three breakdowns. The breakdowns are where
the insight is:

- **by_signal** — average per evaluator. *Divergence is the story.* If
  `confidence` ≫ `back_translation`/`llm_judge`, the model is overconfident. If
  the judge and back-translation disagree, dig into examples.
- **by_language** — where the model is strong vs weak. (Our runs: Swahili >
  Yoruba > Amharic.)
- **by_speaker / domain** — does quality drop on the *instructions* a responder
  gives vs the *reports* a victim sends? In emergency data, the safety-critical
  instructions were exactly where scores dipped — the most important place to
  catch problems.

The **verdict** is a blunt summary (GOOD FIT / CONDITIONAL FIT / NOT A FIT). Any
`risky` item ⇒ NOT A FIT for *unmonitored* use — keep a human in the loop.

Export it: `tafsiri report <run-id> --format md --out findings.md`.

---

## 7. Limitations & pitfalls

- **No single metric is truth.** Each signal is a flashlight, not the sun. Use
  several; trust agreement, investigate disagreement.
- **Reference-free ≠ free of error.** Back-translation and LLM judges both have
  systematic biases (above). They *estimate* quality.
- **Small samples lie.** Ten sentences can't characterize a language. Scale up,
  and report the sample size (the breakdowns include `n`).
- **The judge shares the translator's blind spots** on low-resource languages.
- **Calibrate against humans.** The gold standard is human adequacy judgments;
  treat the automatic score as an approximation and spot-check it.

---

## 8. Using this for research

The design lets you hold the **eval harness fixed** and vary one input:

- **Compare engines** — run the same dataset through `--engine daraja` and
  `--engine llm:claude:...`; compare `by_signal` and `by_language`. (Purpose-built
  vs general LLM is a genuine open question for African languages.)
- **Compare languages** — one engine, many `--langs`; find the weak spots.
- **Compare domains** — run each `samples/` domain; see where quality holds.
- **Stress the methodology** — does back-translation agree with the judge? Where
  they diverge, which is right? That's a paper-sized question on its own.

Everything persists to SQLite, so runs accumulate into a benchmark over time.

---

## 9. Extending the evals

Add your own signal by implementing the `Evaluator` protocol:

```python
class LengthRatioEvaluator:
    name = "length_ratio"
    def evaluate(self, source, translation):
        from tafsiri.schema import EvalSignal
        if not translation.ok or not translation.text:
            return EvalSignal(self.name, None, {"reason": "no text"})
        r = len(translation.text) / max(1, len(source.text))
        score = max(0.0, 1.0 - abs(1.0 - r))   # closer to 1:1 is better
        return EvalSignal(self.name, score, {"ratio": round(r, 2)})
```

Pass it into `run_pipeline(..., evaluators=[...])`, give it a weight in the
`Scorer`, and it shows up in every export automatically. Reference-based metrics
(chrF/COMET) fit the same shape if you have gold references in your dataset.

---

## 10. Glossary

- **Adequacy** — how completely meaning is preserved.
- **Fluency** — how natural/grammatical the output reads.
- **Low-resource language** — little training data; harder to model well.
- **Reference / gold translation** — a known-correct human translation.
- **Reference-free / quality estimation** — judging without a gold reference.
- **Round-trip / back-translation** — translate out and back to compare.
- **Calibration** — how well a confidence score matches real accuracy.
