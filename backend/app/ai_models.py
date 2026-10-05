"""The language models a reading may ask for the final pipe assignment - or none, the sheet's own evidence alone.

Chosen per analysis, so the same drawing can be read once with each and the answers, tokens and cost compared.
"""
import os

NONE = 'none'
ASTRA = 'gpt-6-astra'
OPUS = 'claude-opus-5-5'
CHOICES = (NONE, ASTRA, OPUS)
LABELS = {NONE: 'Utan AI', ASTRA: 'GPT-6 Astra', OPUS: 'Claude Opus 5.5'}


def default():
    """What a reading uses when nobody chose: the rules, unless the operator turned the model on."""
    return ASTRA if os.environ.get('VVS_ASSIGNMENT_MODEL') == '1' else NONE


def available():
    from .source_model import configured as openai_ready
    from .claude_model import configured as claude_ready
    return {NONE: True, ASTRA: openai_ready(), OPUS: claude_ready()}


def transport(choice):
    """The connection that answers the assignment for `choice`; None reads by the rules."""
    if choice == ASTRA:
        from .source_model import transport as openai_transport
        return openai_transport(ASTRA)
    if choice == OPUS:
        from .claude_model import transport as claude_transport
        return claude_transport(OPUS)
    return None
