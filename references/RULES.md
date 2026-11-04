# Rules

The scripts already apply almost all of these. If you see something skip one of them, **stop and tell the user**.
Do not fix it by editing the verifier. Company-specific rules (whom you never contact, what you never claim)
live in the active profile: see `profiles/<name>/RULES.md`.

## What is never done

- **Guess an email.** Only an email published on the company's own site counts: on its own domain, or a
  Gmail, Yahoo or Outlook address the company itself publishes. No `first.last@company.com` deduced, no
  tools that guess addresses. An email that OpenStreetMap carries but the site does not publish is not used.
- **Use as a source** LinkedIn, Google Maps, Yelp, Facebook, Instagram or any directory (Sunbiz, BBB, Manta...).
  They can tell you a company exists, never where its site or email is. `common.DIRECTORIES` drops them.
- **Text or message** (SMS, WhatsApp, DMs) someone who did not write to you first. Telemarketing and messaging
  laws are strict in many places.
- **Contact whoever the profile excludes** (competitors, government, chains, whatever the profile lists).
- **Write to someone already contacted** or who asked not to be contacted. `common.already_contacted()` checks
  `data/contacts.csv`, `data/suppress.txt`, every CSV in `data/imports/` and earlier campaigns.
- **Read pages robots.txt forbids**, or read without a pause between pages of the same site.
- **Send anything.** Not emails, not forms. nosework prepares; the user approves; the user's own tool sends.
- **Edit `verify.py`** or the rules in `draft.py` to make something pass.
- **Skip a captcha.**
- **Print or copy the keys** in `.env`.

## Words that never go in an email

The universal list is in `UNIVERSAL_BANNED` in `scripts/draft.py`: compliments ("excellent", "impressive"),
cliche openers ("I came across your website", "I hope this email finds you"), accusations ("violating",
"out of compliance", "lawsuit") and criticism of their website ("outdated", "ugly", "not mobile friendly").
The profile adds its own in `banned_phrases` (claims you cannot back up). Single words match whole words in the
first line; phrases match as substrings.

## Signals (why they might need you)

Defined by the profile in `signals.json`. `scan.py` finds each one on the company's own pages and keeps the
page and the sentence that prove it. The example profile ships translation-related signals (Hispanic audience,
no Spanish version, bilingual hiring, international work, English-only PDFs, sector confirmation).

## Points

Points = signals + sector priority (priority 1: +2, 2: +1, 3: 0) + size (small or medium: +2, large: +1) + 1 if
the company is 2 years old or less + 1 if the contact is a named person. All the numbers can be changed in the
profile (`scoring`). Below `min_points_for_email` (4 by default) nobody is emailed.

## How an email address is checked before it enters the queue

`scripts/mail.py` does it without sending anything. The ideas come from
[reacherhq/check-if-email-exists](https://github.com/reacherhq/check-if-email-exists) (MIT).

1. **The domain receives mail.** Public DNS (Cloudflare, then Google) is asked whether the domain exists and has
   a mail server (MX). With none, the email would surely bounce and does not enter. If DNS does not answer, it
   does not count as a failure.
2. **Not disposable.** The list is `references/disposable-domains.txt` (disposable-email-domains, CC0).
3. **A named person beats a generic mailbox.** The list of role mailboxes (`info@`, `sales@`, `admin@`...) is
   `references/role-mailboxes.txt` (Reacher, MIT). A generic mailbox is **not discarded**, because in a small
   business `info@` is read by the owner. It only loses against a person.
4. **What cannot be known** without talking to the company's mail server is whether *that mailbox* exists
   ("address not found" bounces). That is not done: from a home connection it is often blocked and looks like
   spam. Some of those bounces will still arrive; add them to `data/suppress.txt`.

## Companies that stay out even with an email

- Those whose site **does not say they are in that state or city** (search brings companies from anywhere).
- **Chains and large companies**: 10 locations or more, or 1,000 employees or more according to their site
  (`max_locations`, `max_employees`).
- Those whose **name does not appear on that site** (the site may belong to another business).
- **Lists, directories and articles** ("Top 23 Food Manufacturers").
- Sites that **redirect to another domain**.

## When a site is dated (for offers about a new website)

`scan.py` measures it from the page itself and keeps the proof of each sign: not mobile friendly (no `meta
viewport`), latest copyright year 5 or more years ago, no HTTPS, no meta description, no `<h1>`, WordPress older
than 6, old technology (Flash, jQuery 1.x, table layout, frames) or no sitemap. **3 or more signs are needed.** It
is an internal fact: it is never said to the company. Only the offer rule `site_dated` reads it.

## Size and age (estimates, never facts)

- **What the company declares for search engines** (schema.org `numberOfEmployees`, `foundingDate`, `founder`)
  goes first, because the company says it itself. Idea taken from
  [scrapinghub/extruct](https://github.com/scrapinghub/extruct) (BSD). About 1 in 8 sites has it.
- **Size** comes from what the site says ("over 50 employees", "team of 12", "3 locations") or from how many
  people its team page shows. Bands: micro (under 10), small (10 to 49), medium (50 to 249), large (250 or more).
  If the site says nothing, it is "unknown". It is not official data. Do not mention it in the email.
- **Age**: first the state registry (optional, `scripts/registry.py`), then what the site says ("since 1998",
  "over 20 years"), then the oldest copyright year, which only says "at least since".

## People

A person is noted only if their name and role are published on the company's site (team page, "about",
schema.org). They are addressed by name only if the chosen email contains their first or last name. Otherwise the
greeting is to the company's team. The person is never searched for anywhere else.

## Sending pace

nosework does not send, but do not load 500 emails into a new mailbox. A new sending domain needs a warm-up and a
daily cap that grows slowly; a bounce marked as spam is serious: stop and look. Sixty to a hundred emails a week is
a reasonable start. If a sector gives no real conversation after about 200 emails, switch it off
(`"active": false` in `sectors.json`) and move its share to another.
