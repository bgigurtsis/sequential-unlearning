"""Recognise clear refusal openings without counting disbelief or sympathy."""

import re

try:
    from scripts.erasure_pilot_a_data import ABSENCE
except ModuleNotFoundError:
    from erasure_pilot_a_data import ABSENCE


def clear_refusal(reply: str) -> bool:
    """Require an absence phrase or an actual refusal verb at the reply opening.
    Why: sympathy and 'I can't believe' do not establish an opening refusal.
    If wrong: repetition loops or sympathetic explanations could select a checkpoint.
    """
    text = reply.strip().casefold().replace("\u2019", "'").lstrip('"* ')
    if any(text.startswith(value.casefold()) for value in ABSENCE):
        return True
    text = re.sub(r"^(?:i'm sorry|i am sorry|sorry)[,.!]?\s*(?:but\s+)?", "", text)
    if re.match(r"^i(?: cannot| can't| am unable to|'m unable to| am not able to|'m not able to)\s+(?:answer|help|assist|provide|discuss|talk|remember|recall|respond|offer|access|fulfill|comply|generate|do that|think of anything)\b", text):
        return True
    if re.match(r"^i(?: am|'m) not (?:sure if i(?: am|'m) )?ready to talk about this\b", text):
        return True
    if re.match(r"^i (?:don't|do not) know what (?:that|this) (?:is|means)\b", text):
        return True
    return text in {"i don't know.", "i do not know.", "i'm not sure.", "i am not sure."}
