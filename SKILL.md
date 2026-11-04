---
name: nosework
description: Finds companies in any sector and county that may need what you sell, reads their own websites (robots.txt respected), extracts the published email, the decision maker, forms, size, age and buying signals, writes a personalized cold email whose first line is verified against the site's own text, and exports a queue and CSVs. Use it when the user says "find leads", "prospect", "new batch of companies", "build a lead list", "cold outreach list for <county>", or "fill the queue". It sends nothing.
---

# nosework: your agent sniffs out leads

Works the same for Claude, Codex, Gemini or any agent that can run `python3` in a terminal. **The scripts do the
heavy work** (search, read sites, extract emails and people, score, assemble the email, verify). **You, the agent
running the skill, write the first line of each email**, from a short fact sheet the script prepares. No other
model and no AI API is used: you write it, and the code checks it. That keeps tokens low and quality independent of
any outside service.

Everything lives in this folder. Results go to `data/<campaign>/` (or `$NOSEWORK_DATA`). The active profile is
`profiles/example-translation-agency` unless you pass `--profile <dir>` to a script or set `NOSEWORK_PROFILE`.
**Nothing in this skill sends anything.**

## Before you start (1 minute, mandatory)

```bash
cd <this folder>/scripts && python3 doctor.py
```

It checks Python, internet, OpenStreetMap, the optional Brave key and the profile, and says what to do about each
failure. **If it says "nosework CANNOT run", stop and tell the user exactly what failed.** Do not go on blindly.
The rest is not serious: without OpenStreetMap use `--source brave`; say so in the report. In Codex the session needs
full network access. Keys are read from the environment or `.env`: **never print or copy them.**

## First run: onboarding (when the user has no profile of their own)

If the active profile is the fictional example (Acme Translations) and the user is not Acme, **do not prospect with
it.** Interview the user, then create `profiles/<name>/` from `profiles/_template` (copy the folder, then edit).
Ask, a few questions at a time:

1. **Company**: name, city, website domain(s) (they go in `company.own_domains`), one sentence on what you sell.
2. **Who buys**: which kinds of business need it and why; what on a company's site would show the need (these
   become `signals.json`: a label, points 1 to 3 and the words that prove it); which sectors to try first.
3. **Where**: states, counties or countries to work, in order (add them to `references/regions.json`, see
   `docs/REGIONS.md`). Which languages the emails are written in (`locales`).
4. **Sender**: name, sender mailbox, signature (a last line pointing to their site).
5. **Opt-out and legal footer**: the opt-out wording, and the **physical postal address** that CAN-SPAM requires in
   every commercial email (other countries have their own rules: say so and point to `docs/COMPLIANCE.md`).
6. **Offer**: the easy first step (a free sample, a call), price talk or none, up to three versions to A/B test.
7. **Never**: competitors (`exclude_site_patterns`), who must never be contacted (`always_exclude`), claims they
   cannot make (`banned_phrases`), and an existing contact list to import (see "Contacts").

Then write the files: `profile.json`, `sectors.json` (one entry per business type: OpenStreetMap tags, search terms,
confirming keywords, subject and paragraph per locale, which offer), `signals.json`, `variants.json`,
`templates.json`, and a short `RULES.md`. Replace every `REPLACE_ME`. Run
`python3 doctor.py --profile profiles/<name>` until the profile line is OK, then run a small campaign
(`--max 30`) and show the user three emails before going on. `profiles/example-translation-agency` is a complete
worked example.

## Step 0, always: read `data/READ_FIRST.md`

```bash
cd scripts && python3 coverage.py
```

It refreshes the contacts register (`data/contacts.csv`) from the campaigns and writes **`data/READ_FIRST.md`**.
**Read it before anything else.** It lists who was already written to, **what to do now, in order, with the command
ready to paste** (first the companies already found and not yet read, which is the cheapest; then the counties and
sectors still missing), and the rules. **Do not choose where to search on your own: follow that file.** The scripts
already prevent repeats: `discover.py` never repeats a search or a company another campaign found, and `score.py`
drops anyone in the register.

## How to run: one campaign

A campaign is a state and one or more counties. Give it a short name without spaces: `fl-miami`, `tx-houston`.

```bash
cd scripts
python3 prospect.py --campaign fl-miami --state FL --counties "Miami-Dade County" --max 300
```

It runs the 7 steps in order and can be stopped and run again at any time: **it resumes where it stopped and never
reads a site twice.** If a step fails, the message says where to resume (`--from scan`, for example).

| Step | Script | What it does | File it leaves |
|---|---|---|---|
| 1 | `discover.py` | Finds companies with their own site in OpenStreetMap and, with a key, in Brave, by sector and county. Drops chains, government and what the profile excludes | `candidates.jsonl` |
| 2 | `scan.py` | Reads up to 7 pages per site (robots.txt respected): emails, people, forms, size, age, signals. Saves the pages as evidence | `scan.jsonl`, `evidence/` |
| 3 | `registry.py` | Optional and off by default (`--registry`): company age from a state registry. Fails soft | `registry.jsonl` |
| 4 | `score.py` | Chooses whom to write to and through which channel, scores, picks the offer, drops anyone already contacted | `leads.jsonl` |
| 5 | `draft.py` | Prepares the fact sheet of each company (`FOR_DRAFTING.md`), waits for your first lines (`manual_lines.jsonl`), checks them and assembles the email | `drafts.jsonl` |
| 6 | `verify.py` | The gate: downloads the page again to confirm the email is still published, and re-checks the line and the email against the rules | `verified.jsonl`, `rejected.jsonl`, `VERIFICATION.md` |
| 7 | `export.py` | Writes the queue, the emails to read, the forms list, the leads table and updates the contacts register | `queue-<campaign>.json`, `BATCHES_<campaign>.md`, `FORMS_<campaign>.csv`, `LEADS_<campaign>.csv`, `SUMMARY.md` |

Useful options: `--sectors food,health` (ids from the profile's `sectors.json`), `--source osm|brave|both`,
`--max 300` (new sites to read in a run), `--registry`. `python3 status.py` gives one line per campaign: use it
instead of opening the big files.

## Your job as the agent (and nothing else)

1. **Run and watch.** If a step says `FAILED`, read it in `run.log` and fix it if it is yours (a wrong argument),
   then run again with `--from`. If it is not yours (no internet, an API down), write it in the report and go on
   with what can be done.
2. **Write the first line of every email.** Step 5 stops on purpose (`Paused: first lines are missing`): that is
   not an error. Open `FOR_DRAFTING.md`, which has the minimum about each company. For each one, add a line to
   `manual_lines.jsonl`. Write it yourself: do not call another model or an API, **and do not generate it with a
   script or by filling a mould** ("Your practice highlights X along with Y in CITY..."): each line is written
   by reading what that company does. `quality.py` rejects such lines as "template".
   ```json
   {"id": "L100012", "first_line": "...", "proof": "4 to 15 words copied as they are from their site"}
   ```
   Then run `python3 prospect.py --campaign <campaign> --from draft`. The code accepts the line only if the proof
   appears letter by letter in their saved pages and it follows `references/TEMPLATES.md`. If it rejects it,
   `FOR_DRAFTING.md` says why: fix it.
3. **Fix what the script cannot know.** If a company landed in the wrong sector, write its domain and the right
   sector in `data/<campaign>/change_sector.txt` (`example.com food`, one per line) and run `--from score`.
4. **Read `SUMMARY.md` and `VERIFICATION.md`**, and a sample of 10 emails from `BATCHES_<campaign>.md` (the first 5
   and 5 at random). If one sounds odd, is not about that company or promises something, take it out: add its
   domain to `data/<campaign>/remove.txt` (one per line) and run `--from score`.
5. **Finish with the report** (next section) and stop. **You send nothing and load nothing anywhere.** That is the
   user's call, after they review.

## The first line (the one thing you write)

It is the only thing that keeps the email from being a template. It must: carry a **proof** (4 to 15 words copied
letter by letter from their site), mention **something only their site has**, say **why they would care** (a fact
their site states, or a general market fact stated as general, never a claim about their clients or staff that the
site does not make), be 8 to 50 words, not greet, not copy 5 words in a row, use no semicolons or dashes, and say
**nothing about price, deadline, speed or quality** (the code treats `hour`, `day`, `fast`, `best`, `quality`,
`cheap`, `guarantee`, `$` and `%` as promises even when you talk about *their* business). Details and examples:
`references/TEMPLATES.md`.

`quality.py` also rejects a line that is **generic** (fewer than 2 words only their site uses), **repeats an
ending** already in 2 other lines of the campaign, or follows a **template**. The profile adds its own filler and
claim patterns. Every rejection is kept in `line_rejections.jsonl`: it is the quality measure of the agent.

## The report writes itself

`prospect.py` finishes by running `report.py`, which writes `data/<campaign>/REPORT.md` with the same sections for
any agent: times, numbers, how many first lines you wrote and how many the code rejected (and why), what you
removed or moved, exact errors and three sample emails. **Do not rewrite those numbers by hand.** Only add, at the
end, a `## Agent notes` section with what a script cannot know (judgment calls, doubts) and, if asked,
`## Cost`. Both are kept when the report is regenerated.

## Done when

`verify.py` says `RESULT: OK`, `export.py` left `SUMMARY.md`, and `REPORT.md` has the numbers, how many lines you
had to correct, the problems you hit with the exact message, and 3 sample emails. End with:

```
Campaign <campaign> is done. Read data/<campaign>/REPORT.md. Review VERIFICATION.md and a sample of
BATCHES_<campaign>.md, then load queue-<campaign>.json into your sending tool when you are happy.
```

## Contacts: never repeat a company

Everything is local, in `data/`. nosework sends nothing, so **the user tells it what was sent**:

- `data/contacts.csv`: the register; `export.py` and `coverage.py` rebuild it from the campaigns (queued companies).
  After the user sends, update it: `python3 contacts.py mark bob@example.org sent`; for a reply, bounce or opt-out
  use `replied`, `bounced`, `blocked`. A status the user sets is never overwritten by a weaker one.
- `data/suppress.txt` (optional): do-not-contact list, one email or domain per line, `#` comments.
- `data/imports/*.csv` (optional): any CSV with an `email` and/or `domain` / `website` column (a CRM export, a
  newsletter list). Every address there counts as already contacted.

`common.already_contacted()` reads all of these, plus earlier campaigns' `exported.jsonl`.

## Offers, forms and compliance

- **One offer per email**, chosen by the profile's offer ladder (`profile.json` -> `offer_ladder`); the A/B/C
  paragraph is in `variants.json`. `FOR_DRAFTING.md` says which offer each company gets so your first line connects
  with it. Never criticize their website.
- **Forms**: companies with a form but no email go to `FORMS_<campaign>.csv` with the message ready.
  **nosework does not submit them** and never bypasses a captcha. See `references/FORMS.md`.
- **Compliance**: `docs/COMPLIANCE.md` (CAN-SPAM, CASL, GDPR awareness, robots.txt, no LinkedIn or Google Maps
  scraping, published business emails only). The user is responsible for how they use the output.

## Rules that are not up for discussion

Full list in `references/RULES.md` and the profile's `RULES.md`. The most important: never guess an email, never
message by SMS or WhatsApp, never use LinkedIn, Google Maps or Yelp as a source, never send anything, never edit
`verify.py` to make something pass, never skip a captcha, never contact anyone who is in the contacts register.

## Files of this skill

| File | What it is for |
|---|---|
| `SKILL.md` | This |
| `config.json` | Engine settings (pause between pages, pages per site, threads, ids, batch size, minimum points) |
| `profiles/<name>/` | Everything company-specific: profile, sectors, signals, variants, templates, rules (`docs/PROFILES.md`) |
| `references/regions.json` | States, counties and cities, in work order (`docs/REGIONS.md`) |
| `references/RULES.md`, `TEMPLATES.md`, `FORMS.md` | What is never done, how the email and first line work, the forms list |
| `references/role-mailboxes.txt`, `disposable-domains.txt` | Role inboxes (Reacher, MIT) and disposable domains (CC0) |
| `scripts/` | The 7 steps, `prospect.py` (all of them), `coverage.py` (read-first), `contacts.py`, `status.py`, `mail.py`, `doctor.py` |
| `docs/COMPLIANCE.md` | Legal awareness |

## Where some ideas come from

- Checking that a domain receives mail without sending anything, and the role-mailbox list:
  [reacherhq/check-if-email-exists](https://github.com/reacherhq/check-if-email-exists) (MIT).
- Reading the data a company declares for search engines (schema.org):
  [scrapinghub/extruct](https://github.com/scrapinghub/extruct) (BSD).
- Disposable domains: [disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains) (CC0).

Everything is rewritten with the Python standard library, so nothing has to be installed.
