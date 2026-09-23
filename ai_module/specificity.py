"""Conservative lexical cues for concrete source facts, not relevance scores.

The model still selects and orders every candidate. These rules only narrow the
quotes to experience, scale or services when the profile supplies them.
No profile IDs, preferred contractors or new factual claims are encoded here.
"""

import re


_CONCRETE = re.compile(
    r"\b\d[\d ]*\+?\s*(?:лет|года?\b|гостей|человек|заказов|мест\b|мероприятий)"
    r"|акт[её]р\w*\s+(?:театра|кино)|педагог|препода\w*|солист"
    r"|телевидени\w*|телеканал\w*|радиостанци\w*"
    r"|(?:специализир\w*|вед[её]т|веду|провод\w*|пров[её]л)\b[^.!?]*"
    r"(?:корпоратив\w*|делов\w*|форум\w*|конференци\w*)"
    r"|тимбилдинг\w*|обряд\s+первых\s+шагов"
    r"|без\s+(?:\w+\s+){0,2}(?:речей|тостов|конкурсов)|развлечения\s+и\s+танцы"
    r"|\bdj\b|квиз\w*|интерактив\w*|сценари[йя]\b|оборудовани\w*"
    r"|вместимост\w*|кейтеринг|парковк\w*|террас\w*|вид\w*\s+на\s+[^.!?]*горы"
    r"|(?:клиент\w*|партн[её]р\w*)\s*:|оформление\s+для\b",
    re.IGNORECASE,
)
_LANGUAGES = re.compile(r"\b(?:казахск|русск|английск)\w*", re.IGNORECASE)


def distinctive_evidence_ids(candidate_id: str, evidence: dict[str, str]) -> list[str]:
    """Return concrete quote IDs, or all description IDs if no cue is found.

    This is a heuristic, not a truth/uniqueness guarantee. Unknown wording must
    not exclude a contractor or cause fallback solely for lack of numeric facts.
    Full evidence is always sent to the model for the actual ranking decision.
    """
    description = [ref for ref in evidence if ref.startswith(f"{candidate_id}:description:")]
    concrete = [ref for ref in description if (
        _CONCRETE.search(evidence[ref])
        or len({word.casefold() for word in _LANGUAGES.findall(evidence[ref])}) >= 2
    )]
    return concrete or description or list(evidence)
