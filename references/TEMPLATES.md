# The email

One fixed structure; the only part that is truly about the company is the **first line**. `scripts/draft.py`
assembles it. Everything else comes from the active profile.

```
{greeting: the contact's first name | "the <company> team" | nothing}

{first line: one concrete detail from THEIR site, connected with why they would care}

{sector paragraph: what you do for this kind of business (sectors.json -> block)}

{the offer: variants.json, A/B/C test; two sentences: paragraph, then one short question}

{signature (profile.json -> sender.signature)}

{opt-out line + legal footer with your physical address (sender.opt_out)}
```

- **Language**: if the site declares one of the profile's `locales` in `<html lang>`, the email is written in it;
  otherwise in `default_locale`.
- **Subject**: the sector's own (or the alternate offer's), lowercase and without a sales hook.
- **One offer per email**, chosen by the offer ladder in the profile (`offer_ladder`): partner sectors always get
  their own offer; otherwise the rules are tried top to bottom and the first match wins.
- **Never criticize their website** ("old", "ugly", "not mobile friendly"): it offends and can be used against you.
  Talk about what they gain. The code rejects those words.
- **Prices**: only what the profile's variants say. Do not invent numbers in the first line (the code rejects
  `$`, `%`, `hours`, `days`, `fast`, `best`, `quality`, `cheap`, `guarantee`...).

## The first line

It is what keeps the email from being a template. **The agent running the skill writes it**, never another model
or an external API. The code accepts it only if:

1. **It brings a proof**: 4 to 15 words copied *letter by letter* from their site, where the detail you mention
   appears. If the proof is not in the saved pages, it is rejected.
2. **It mentions something only their site has**: a product, a service, a type of customer, a project, an area
   they serve. An address, opening hours or "their site is modern" do not count. **Test for generic**: change the
   company's name; if the sentence is still true of any other company, it is generic. Rewrite it.
3. **It says why they would care** about what you sell, without yet saying what you offer (that is the next
   paragraph). Two valid forms, and only two:
   - **Something their site says** (they export abroad, they hire for a skill you cover, the owner comes from
     another country...).
   - **A general market fact, stated as general**. **Never a claim about their clients or staff that their site
     does not make.** The profile can list patterns for fillers and claims to reject (`quality` section).
   A line that only describes their business, with no reason to care, falls short.
4. **8 to 50 words**, no greeting, does not copy 5 consecutive words from their site, no semicolons or dashes,
   and **no price, deadline, speed or quality talk**.

`quality.py` adds three universal checks: it is **not generic** (at least 2 words that only that site uses), it
does **not repeat an ending** already in 2 other lines of the campaign, and it is **not a template** (the same
frame as 2 or more other lines with words swapped in).

Tone examples (fictional companies, a translation vendor writing):

- *(food maker)* "Your site says you co-pack sauces for restaurant groups, and in this area many kitchen teams work in Spanish."
- *(roofing)* "I saw the roofing crews you run across the county, and safety talks land better in the language the crew thinks in."

Rejected examples:

- "I came across your website and was impressed." (generic, flattery)
- "We offer fast, high-quality services." (offer and promise in the first line)
- "Your company is a leading manufacturer in the area." (copies and fits anyone)

## The message for forms

For companies that only have a contact form, `draft.py` leaves a shorter message in `FORMS_<campaign>.csv`: the
first line, the sector paragraph, the offer and "My email: <mailbox>". No greeting or opt-out line, because the form
already carries the sender's name and email. **nosework does not submit forms.**
