from types import SimpleNamespace

from case_digest.telegram_reader import _reaction_total


def test_reaction_total_supports_pyrogram_list():
    reactions = [SimpleNamespace(count=2), SimpleNamespace(count=3)]

    assert _reaction_total(reactions) == 5


def test_reaction_total_supports_wrapped_reactions():
    reactions = SimpleNamespace(reactions=[SimpleNamespace(count=4)])

    assert _reaction_total(reactions) == 4
