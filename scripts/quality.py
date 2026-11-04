"""Quality checks on a first line that need no AI.

  specific      the line uses at least two words that are on that company's own site and rare across the
                campaign's sites (Vocabulary). "dulce de leche", "blue crab" or "food trucks" make a line theirs;
                "air conditioning" or "residents" are on every site, so a line made of them is true of any
                company: generic.
  repeated      its second half (what comes after the last comma) already appears in 2 other lines of the
                campaign: a formula the reader would notice if two companies compared their emails.
  template      the line follows the same frame as 2 or more other lines of the campaign once the words that
                change are taken out ("Your practice highlights X along with Y in CITY, and ..."). A script
                filling one frame with rare words passes every other check while reading as nonsense.
  vague why     (profile) the reason given is a tag that fits any company in the region. The profile lists the
                patterns (quality.vague_reason_patterns) and what exempts a line (a concrete market it serves).
  claim         (profile) it states something about their clients or staff that their site doesn't say.
The first three rules are universal and live here; the last two come from the profile (profile.json -> quality).
problems() returns the reasons in English, like draft.line_problems(); an empty list means the line passes.
"""
import re

from common import PROFILE, norm

QUALITY = PROFILE.get('quality', {})

STOP = set('''a an the and or of to in on for with from by at as is are was were be been it its this that these those
your you we our they their them his her he she i my me so such than then there here also more most many much
lot lots some any every each all both very just only into onto over under about across through who whom which what
when where why how not no nor but if while since because can could will would may might must should has have had
do does did de la el los las y o en con por para del al su sus un una que es son se lo le les muy m\u00e1s'''.split())
# Words that say what kind of business or where, never which business: they don't make a line specific.
GENERIC = set('''area areas region company companies business businesses firm firms team teams service services work works
working client clients customer customers people community industry local family owned family-owned years since site
website page'''.split()) | {w.lower() for w in QUALITY.get('generic_words', [])}


def _rx(patterns: list[str]):
    return re.compile('|'.join(f'(?:{p})' for p in patterns), re.I) if patterns else None


VAGUE_WHY = _rx(QUALITY.get('vague_reason_patterns', []))
REASON_EXEMPT = _rx(QUALITY.get('vague_reason_exempt_patterns', []))
CLAIMS = [re.compile(p, re.I) for p in QUALITY.get('unsupported_claim_patterns', [])]


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", norm(text).replace("'s", ' '))


def stem(w: str) -> str:
    """Crude plural/verb folding so 'restaurants' meets 'restaurant' and 'installing' meets 'installation'."""
    for suf in ('ations', 'ation', 'ings', 'ing', 'ers', 'er', 'es', 's'):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def content(text: str) -> set[str]:
    return {stem(w) for w in words(text) if len(w) >= 3 and w not in STOP and w not in GENERIC}


class Vocabulary:
    """Which words each company's saved pages use, and on how many sites of the campaign each word appears."""

    def __init__(self, camp):
        from common import page_text
        self.by_site, self.df, self.sample = {}, {}, {}
        root = camp / 'evidence'
        for d in (root.iterdir() if root.exists() else []):
            text = ' '.join(page_text(p.read_text(encoding='utf-8', errors='ignore')) for p in d.glob('*.html'))
            ws = content(text)
            self.by_site[d.name] = ws
            for w in words(text):  # one readable spelling per stem, to show the agent which words are "theirs"
                if len(w) >= 3 and w not in STOP and w not in GENERIC:
                    self.sample.setdefault((d.name, stem(w)), w)
            for w in ws:
                self.df[w] = self.df.get(w, 0) + 1
        self.limit = max(3, int(0.15 * len(self.by_site)))

    def rare_words(self, site: str, company: str, n: int = 14, text: str = '') -> list[str]:
        """Words that few sites of the campaign use, taken from what describes the company (its summary) when
        given: names, license numbers and typos elsewhere on the site are rare too, but say nothing."""
        skip = content(company)
        pool = (content(text) & self.by_site.get(site, set())) if text else self.by_site.get(site, set())
        cand = [w for w in pool if w not in skip and self.df.get(w, 0) <= self.limit and not re.search(r'\d', w)]
        cand.sort(key=lambda w: (self.df.get(w, 0), w))
        return [self.sample.get((site, w), w) for w in cand[:n]]

    def own(self, line: str, site: str, company: str) -> set[str]:
        mine = self.by_site.get(site, set())
        return {w for w in content(line) - content(company) if w in mine and self.df.get(w, 0) <= self.limit}


def tail(line: str) -> str:
    """What comes after the last comma, first 7 words: where a formula repeats ('..., and many residents ask for it')."""
    part = norm(line).rsplit(',', 1)[-1]
    part = re.sub(r'^\s*(and|where|so|while|y|donde)\s+', '', part)
    return ' '.join(words(part)[:7])


FRAME_SHARE = 0.2   # a word is part of the frame when it is in at least this share of the campaign's lines
FRAME_MIN = 7       # frames shorter than this are just "your ... in ... and ...": too common to mean a template


def frame(line: str, common: set[str]) -> tuple[str, ...]:
    """The line with the words that change from company to company taken out."""
    return tuple(w for w in words(line) if w in common)


def template_hits(line: str, others: list[str]) -> int:
    """How many other lines share this line's frame (see 'template' above)."""
    if len(others) < 5:
        return 0
    df = {}
    for o in others:
        for w in set(words(o)):
            df[w] = df.get(w, 0) + 1
    common = {w for w, n in df.items() if n >= FRAME_SHARE * len(others)}
    mine = frame(line, common)
    if len(mine) < FRAME_MIN:
        return 0
    return sum(1 for o in others if frame(o, common)[:FRAME_MIN + 3] == mine[:FRAME_MIN + 3])


def problems(line: str, proof: str, company: str, others: list[str], vocab: 'Vocabulary | None' = None,
             site: str = '') -> list[str]:
    p = []
    own = vocab.own(line, site, company) if vocab else content(proof) & content(line)
    if len(own) < 2:
        p.append('generic: it hardly uses words that are particular to their site (what they do, sell or whom they serve); '
                 'changing the company name would make it fit any company in their sector')
    t = tail(line)
    if t and len(t.split()) >= 4 and sum(1 for o in others if tail(o) == t) >= 2:
        p.append(f"the ending '{t}...' is already in 2 or more emails of this campaign: say it in other words")
    if template_hits(line, others) >= 2:
        p.append('template: it follows the same structure as 2 or more lines of this campaign with other words dropped in; '
                 'write it from what that company does, not by filling a mould')
    if VAGUE_WHY and VAGUE_WHY.search(line) and not (REASON_EXEMPT and REASON_EXEMPT.search(line)):
        p.append('the reason given is filler that fits any company in the region. Use something from their site or a '
                 'concrete fact about their city or their customers\' situation')
    if any(c.search(line) for c in CLAIMS):
        p.append('claims something about their clients or staff that their site does not say. '
                 + QUALITY.get('unsupported_claim_hint', 'State it as a general market fact instead.'))
    return p
