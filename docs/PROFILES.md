# Profiles

Everything that is specific to a company lives in one folder under `profiles/`. The scripts contain no company
names, offers, signatures or word lists. Choose the active profile with `--profile <dir>` on any script, or the
`NOSEWORK_PROFILE` environment variable. The default is `profiles/example-translation-agency` (a fictional company).

| File | What it holds |
|---|---|
| `profile.json` | Who you are, sender mailbox, signature and opt-out line (with your legal footer), locales, user agent, exclusion patterns, banned phrases, scoring, the offer ladder, quality settings |
| `sectors.json` | The types of business to find: OpenStreetMap filters, web search terms, confirming keywords, subject and paragraph per locale, which offer; plus `always_exclude` |
| `signals.json` | The buying signals: label, points and a detector each (terms, patterns, phrases, pages, PDF links, sector keywords) |
| `variants.json` | The offer paragraphs with their A/B/C variants, per locale |
| `templates.json` | The greeting per locale and the short message for contact forms |
| `RULES.md` | Your own rules, in prose: whom you never contact, what you never say |

Keys that start with an underscore are documentation and are ignored.

## Make your own

1. Copy `profiles/_template` to `profiles/<your-company>`.
2. Fill every `REPLACE_ME` (the agent does it for you in the onboarding interview described in `SKILL.md`).
3. Run `python3 scripts/doctor.py --profile profiles/<your-company>`: it says what is still missing.
4. Try a small campaign: `--max 30` on the scan step, read the emails in `BATCHES_<campaign>.md`, adjust.

## Signals

A signal is one object in `signals.json`:

```json
{"id": "X", "label": "hires a bookkeeper", "points": 3, "page_types": ["jobs"], "terms": ["bookkeeper"]}
```

`terms` are lowercase substrings searched in the body sentences of the pages (menus are ignored), `patterns` are
regexes on those sentences, `phrases` are searched in the whole page text. `page_types` limits where to look
(`home`, `contact`, `about`, `team`, `services`, `jobs`, `alt_language`, `documents`). `kind` can be `pdf_links`
or `sector_keywords`. `requires` lists signal ids that must match first and `needs_absent: "alt_version"` means the
site must lack the version you would sell. Each hit keeps the page and the sentence that prove it, and the agent
sees them when it writes the first line.

## Offer ladder

`offer_ladder` in `profile.json` chooses one offer per email: `partner_offers` always win; `rules` are tried top
to bottom (first match wins) with conditions on sectors, signals, whether the site has the alternate version and
whether the site is dated; `alternates` define extra offers with their own subject, paragraph and link. An empty
ladder means every company gets its own sector's offer.
