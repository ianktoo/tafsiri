"""tafsiri — generate and evaluate African-language translation data.

Pipeline: source text -> translate (Daraja/Babel) -> evaluate -> structured
training data + eval report.

Public API mirrors the module layout (one concern per module):
    - sources    : load source text (JSONL/CSV) into SourceRecords
    - providers  : translation backends (Translator protocol; DarajaTranslator)
    - evaluators : quality signals (confidence, back-translation, LLM-as-judge)
    - scoring    : combine signals into an aggregate score + rating
    - export     : write training data (chat + pairs) and eval reports
    - pipeline   : orchestrate the above end to end
"""

from tafsiri.schema import (
    EvalResult,
    EvalSignal,
    SourceRecord,
    TranslatedRecord,
    Translation,
)

__version__ = "0.0.1"

__all__ = [
    "SourceRecord",
    "Translation",
    "EvalSignal",
    "EvalResult",
    "TranslatedRecord",
    "__version__",
]
