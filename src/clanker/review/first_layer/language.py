"""Is the README prose in English? Deterministic, no model and no dependency.

Shipwrights reject READMEs whose prose isn't English (code, identifiers and UI strings
don't count) unless an English version is linked. Low English-word density alone is not
enough (terse feature lists have few stopwords), so a reject also needs positive evidence
of another language: its common words, or mostly non-Latin script.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EN = set(
    "the a an and or of to in on for with is are was were be been it its this that these "
    "those you your we our i my me can will how what when which from by as at use using "
    "if not but all has have do does there their they he she run project app".split()
)
# Small high-frequency word lists for the languages most often seen in ships.
OTHER = {
    "spanish": "el la los las de que y en un una es por con para del se su al lo como más "
    "pero sus le ya o este esta proyecto puedes usar cómo",
    "portuguese": "o a os as de que e do da em um uma é para com não por mais dos das se na "
    "no ao seu sua projeto você como usar",
    "french": "le la les de des et un une est pour dans que qui pas sur au aux du en ce cette "
    "vous avec projet comment utiliser",
    "german": "der die das und ist nicht ein eine zu mit von den dem des auf für sich auch "
    "wird werden sie es ich du projekt wie",
    "italian": "il lo la gli le di e che un una per con non sono del della è come questo "
    "progetto puoi usare",
    "indonesian": "dan yang di ini itu dengan untuk dari ke tidak ada akan bisa pada juga "
    "atau saya kamu proyek cara menggunakan",
    "turkish": "ve bir bu da de ile için çok olan gibi daha ama ne kadar proje nasıl "
    "kullanmak",
    "dutch": "de het een en van is dat op te in met voor niet zijn je ook als maar project",
    "vietnamese": "và của là có không được một các cho này những với trong để người dự án",
    "polish": "i w na z że do się nie to jest jak co ale o po projekt",
}
OTHER_WORDS = {lang: set(words.split()) for lang, words in OTHER.items()}

MIN_WORDS = 40
EN_MAX = 0.08  # English stopword share at or above this means English prose
OTHER_MIN = 0.12  # share of one other language's stopwords
NON_LATIN_MIN = 0.5  # share of words in a non-Latin script (CJK, Cyrillic, Devanagari, ...)
MIN_CJK_CHARS = 80
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")

_ENGLISH_LINK = re.compile(
    r"\[[^\]]*(english|\ben\b|🇬🇧|🇺🇸)[^\]]*\]\([^)]*\)|readme[._-]?en\b|readme[._-]english",
    re.I,
)


@dataclass(frozen=True, slots=True)
class LanguageGuess:
    english: bool
    language: str  # "english", a key of OTHER, "non-latin", or "unknown"
    words: int
    english_share: float


def _prose(markdown: str) -> str:
    text = re.sub(r"```.*?```|~~~.*?~~~", " ", markdown, flags=re.S)  # code blocks
    text = re.sub(r"`[^`]*`", " ", text)  # inline code
    text = re.sub(r"<[^>]+>", " ", text)  # HTML tags
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # images
    text = re.sub(r"\]\([^)]*\)", "] ", text)  # link targets (keep link text)
    return re.sub(r"https?://\S+", " ", text)


def _latin(word: str) -> bool:
    return all(ch.isascii() or "À" <= ch <= "ɏ" or "Ḁ" <= ch <= "ỿ"
               for ch in word)  # fmt: skip


def guess_readme_language(markdown: str) -> LanguageGuess:
    prose = _prose(markdown)
    words = [w.lower() for w in re.findall(r"[^\W\d_]+", prose)]
    # Chinese/Japanese/Korean have no spaces between words: count characters instead.
    letters = [ch for ch in prose if ch.isalpha()]
    cjk = sum(bool(_CJK.match(ch)) for ch in letters)
    if cjk >= MIN_CJK_CHARS and cjk / len(letters) >= NON_LATIN_MIN:
        english_share = sum(w in EN for w in words) / max(len(words), 1)
        return LanguageGuess(False, "cjk", cjk, english_share)
    if len(words) < MIN_WORDS:
        return LanguageGuess(True, "unknown", len(words), 0.0)
    english_share = sum(w in EN for w in words) / len(words)
    if english_share >= EN_MAX:
        return LanguageGuess(True, "english", len(words), english_share)
    non_latin = sum(not _latin(w) for w in words) / len(words)
    if non_latin >= NON_LATIN_MIN:
        return LanguageGuess(False, "non-latin", len(words), english_share)
    shares = {lang: sum(w in s for w in words) / len(words) for lang, s in OTHER_WORDS.items()}
    lang, share = max(shares.items(), key=lambda kv: kv[1])
    if share >= OTHER_MIN:
        return LanguageGuess(False, lang, len(words), english_share)
    return LanguageGuess(True, "unknown", len(words), english_share)


def readme_not_english(markdown: str) -> LanguageGuess | None:
    """The guess when the README prose isn't English and no English version is linked."""
    if _ENGLISH_LINK.search("\n".join(markdown.splitlines()[:25])):
        return None
    guess = guess_readme_language(markdown)
    return None if guess.english else guess
