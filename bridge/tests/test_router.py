"""Q9 model yonlendirici: kucuk duzenleme -> Sonnet, yeni buyuk yapi -> Opus, zorlama isareti, ayar onceligi."""
import pytest

from usta.router import OPUS, SONNET, choose, effort_for

NEW_BIG = [
    "önüme devasa modern güzel bir ev yap",
    "bu tepeye bahçeli bir Osmanlı konağı yap",
    "avlulu, kubbeli ve minareli küçük bir cami yap",
    "surlu bir ortaçağ kalesi, kuleleri ve kapısıyla yap",
    "fütüristik cam bir gökdelen ve çevresine meydan kur",
    "200×200 yollarla bir şehir bloğu yap",
    "ahırı, tarlası ve çitleriyle bir çiftlik inşa et",
]
SMALL_EDIT = [
    "çatıyı daha sivri yap",
    "şu odayı modern bir mutfak olarak döşe",
    "pencereleri biraz genişlet",
    "kapının önüne bir fener ekle",
    "duvarı beyaza boya",
]
WORLD = ["akşam olsun", "yağmur yağsın", "beni terasa ışınla", "gece yap"]
QUESTIONS = ["neredeyim?", "bana haritayı göster", "evin fotoğrafını çek"]


@pytest.mark.parametrize("text", NEW_BIG)
def test_new_big_build_goes_to_opus(text):
    m, _, why = choose(text)
    assert m == OPUS, (text, why)
    assert effort_for(m, why) == "medium"


@pytest.mark.parametrize("text", SMALL_EDIT)
def test_small_edit_goes_to_sonnet(text):
    m, _, why = choose(text)
    assert m == SONNET, (text, why)
    assert effort_for(m, why) == "low"


@pytest.mark.parametrize("text", WORLD + QUESTIONS)
def test_world_actions_and_questions_go_to_sonnet(text):
    assert choose(text)[0] == SONNET


@pytest.mark.parametrize("prefix,model", [("!opus ", OPUS), ("!o ", OPUS), ("!sonnet ", SONNET), ("!s ", SONNET)])
def test_force_prefix_overrides_and_is_stripped(prefix, model):
    m, clean, why = choose(prefix + "çatıyı daha sivri yap" if model == OPUS else prefix + "önüme devasa bir kale yap")
    assert m == model and why == "zorlandı"
    assert not clean.startswith("!")


@pytest.mark.parametrize("text,model,rest", [
    ("!haiku önüme ev yap", "claude-haiku-5-5", "önüme ev yap"), ("!h önüme ev yap", "claude-haiku-5-5", "önüme ev yap"),
    ("!fable önüme ev yap", "claude-fable-5-1", "önüme ev yap"), ("!f önüme ev yap", "claude-fable-5-1", "önüme ev yap"),
    ("haiku: önüme ev yap", "claude-haiku-5-5", "önüme ev yap"), ("Haiku 5.5 önüme ev yap", "claude-haiku-5-5", "önüme ev yap"),
    ("fable 5.1: önüme ev yap", "claude-fable-5-1", "önüme ev yap"), ("sonnet 5.5 bir kale yap", SONNET, "bir kale yap"),
    ("opus önüme ev yap", OPUS, "önüme ev yap")])
def test_all_four_models_can_be_forced(text, model, rest):
    m, clean, why = choose(text)
    assert (m, clean, why) == (model, rest, "zorlandı")


@pytest.mark.parametrize("text,model,effort,rest", [
    ("!yüksek önüme ev yap", None, "high", "önüme ev yap"), ("!sonnet !yüksek önüme ev yap", SONNET, "high", "önüme ev yap"),
    ("!max !opus önüme ev yap", OPUS, "max", "önüme ev yap"), ("!h !düşük çatıyı boya", "claude-haiku-5-5", "low", "çatıyı boya"),
    ("haiku: !cokyuksek bir kule", "claude-haiku-5-5", "xhigh", "bir kule"), ("!orta bir köprü", None, "medium", "bir köprü"),
    ("önüme ev yap", None, None, "önüme ev yap"), ("!fable 5.1 !yuksek kale", "claude-fable-5-1", "high", "kale")])
def test_effort_and_model_prefixes_in_any_order(text, model, effort, rest):
    from usta.router import parse_prefix
    assert parse_prefix(text) == (rest, model, effort)


def test_effort_prefix_does_not_reach_claude_text():
    m, clean, _ = choose("!yüksek önüme devasa bir kale yap")
    assert clean == "önüme devasa bir kale yap" and m == OPUS


def test_plain_requests_and_turkish_o_are_not_forced():
    assert choose("o evi biraz büyüt")[2] != "zorlandı"
    assert choose("önüme devasa modern bir ev yap")[0] == OPUS


def test_setting_preference_applies_without_force():
    assert choose("çatıyı daha sivri yap", pref="opus")[0] == OPUS
    assert choose("önüme devasa bir kale yap", pref="sonnet")[0] == SONNET
    assert choose("!o çatıyı sivri yap", pref="sonnet")[0] == OPUS     # zorlama ayari yener
