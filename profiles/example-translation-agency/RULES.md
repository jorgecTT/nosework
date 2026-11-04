# Rules of this profile (Acme Translations, a fictional company)

Whom the example profile never contacts, and what it never says. These are examples: replace them with your own in
your profile. The universal rules are in `references/RULES.md`.

## Never contact

- Law firms (decision of the example company: another channel handles them), government offices, public schools,
  large hospitals and chains. See `sectors.json` -> `always_exclude`.
- Other translation, interpreting or localization companies (`exclude_site_patterns` in `profile.json`).
- Anyone in `data/contacts.csv` as queued, sent, replied, auto_reply, bounced or blocked.

## Never say (see `banned_phrases` in `profile.json`)

- That the translators are "human", "native speakers" or "certified translators": the example company holds no such
  credential and must not imply one.
- That the translation is "official". The company issues a signed certificate of accuracy and says exactly that.
- Anything about a customer's own translation being wrong or non-compliant.

## Offers

The offer ladder (`offer_ladder` in `profile.json`):

1. Partner sectors (accountants, web agencies, funeral homes) always get the offer of their own sector.
2. Public-facing sectors whose site has no Spanish version get the **localization** offer (their home page,
   translated for free as a sample).
3. A site that shows document work (bilingual hiring, English-only PDFs, work with other countries) gets the
   sector's document translation offer.
4. A site that says it serves Spanish speakers but has no Spanish version gets the localization offer.
5. **New website** is a fallback and is switched off (`"active": false`).

Prices and terms in `variants.json` are made up for the example.
