# Compliance

**You are responsible for how you use the leads nosework helps you find and the emails it helps you write.**
This page is awareness, not legal advice. Laws differ by country, state and type of recipient, and they change.
Ask a lawyer before a campaign if you are unsure.

## What the tool does and does not do

- **It sends nothing.** No emails, no form submissions, no messages. It prepares a queue and a list for you to
  review. Sending, and everything that follows from it, is your decision and your tool.
- It reads **public business websites** and notes what they publish: a business email, a named role, a contact
  form. It reads them like a polite visitor: **robots.txt is respected**, there is a pause between pages of the
  same site, at most a handful of pages per site, and it identifies itself with a User-Agent you set in your profile.
- It never uses **LinkedIn, Google Maps, Yelp, Facebook, Instagram** or business directories as a source, and it
  does not log in anywhere. They are dropped by the discovery step (`DIRECTORIES` in `scripts/common.py`).
- **Published business emails only.** It never guesses an address (`first.last@company.com`), never buys or
  imports lists, and never reads an address that the site itself does not publish. It stores the page where each
  email was found, as evidence, in `data/<campaign>/evidence/`.
- It does not check whether a mailbox exists by talking to the mail server (no SMTP probing).

## What you must do

### United States: CAN-SPAM
Commercial email to a business is covered. In every message: do not use false or misleading headers or subject
lines, identify the message as an advertisement where required, include **a valid physical postal address**,
include a **clear, working way to opt out** and honor it within 10 business days. Do not sell or transfer the
addresses of people who opt out. The template profile asks for your address and an opt-out line in every email, and
`verify.py` rejects an email without them. Put the people who opt out in `data/suppress.txt`.

### Canada: CASL
CASL is stricter than CAN-SPAM. Sending a commercial electronic message to a business address in Canada generally
needs consent, express or implied. Implied consent for a published business address is narrow (the address must
be published without a "no unsolicited messages" notice, and your message must be relevant to the person's
role). If you target Canada, get advice and keep the `suppress.txt` list current.

### European Union and United Kingdom: GDPR, ePrivacy, PECR
Business email addresses that identify a person (`name@company.com`) are personal data. You need a lawful basis
(often legitimate interest for B2B), you must tell the person where you got their data and let them object, and
some member states require prior consent even for B2B email. Sole traders and some partnerships are treated as
consumers in the UK. Do not run campaigns in these regions without legal review.

### Everywhere
- Honor opt-outs **forever**: record them with `python3 scripts/contacts.py mark <email-or-domain> blocked` or in
  `data/suppress.txt`. The scripts will never prepare another first email for them.
- Do not text or message (SMS, WhatsApp, social DMs) people who did not contact you first: telemarketing and
  messaging laws are strict.
- Keep records of where each address came from (the evidence folder does that) and delete data when asked.
- Respect a site owner who asks you to stop: add the domain to `data/suppress.txt`.
- Warm up a new sending domain slowly and watch bounces and spam complaints (see `references/RULES.md`).
- Do not claim credentials, results or affiliations you do not have. The profile's `banned_phrases` exist for this.

## Third-party data and terms

- OpenStreetMap data is ODbL (attribution required if you republish it). The public Overpass API has usage
  limits; discovery waits between queries and uses a mirror when one is down.
- The Brave Search API has its own terms and rate limits; you bring your own key.
- State registry lookups use public open-data endpoints (see `docs/REGIONS.md`) and are off by default.
