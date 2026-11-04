# nosework

**Your AI agent sniffs out leads.** An agent skill (Claude Code, Codex, Gemini or any agent that can run `python3`) that builds a verified B2B prospect list and personal cold emails for *your* business, and sends nothing.

![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.10%2B-blue) ![deps](https://img.shields.io/badge/dependencies-none-brightgreen) ![tests](https://img.shields.io/badge/tests-75%20passing-brightgreen)

## Why

Most lead tools sell you a list of guessed emails and a template that says "I loved your recent post". Both burn your domain and your reputation. nosework does the opposite:

- **Only published emails.** It reads each company's own website and takes the address they publish. It never guesses `name@company.com`.
- **A first line that is proven.** Your agent writes one personal sentence per company, and the code only accepts it if a 4 to 15 word quote from the company's site backs it up. Generic lines, templated lines and invented claims about their customers are rejected.
- **Signals you define.** What shows a company needs what you sell (bilingual hiring, no Spanish site, a permit page, a fleet of trucks) is data in a profile, not code.
- **Nothing is sent.** It prepares a queue and CSVs. You review, then send with your own tool.
- **Zero dependencies.** Python standard library only. No API model calls: your agent is the writer.

## How it works

```
discover -> scan -> registry -> score -> draft -> verify -> export
   |          |         |         |        |         |        |
 OpenStreetMap  robots.txt-   founding  who to     agent writes   re-fetch  queue, CSVs,
 + Brave (opt.) respecting     date     write,     the first line the page,  report
                reader                  which offer + quote proof  re-check
```

Every step is resumable. A site is never read twice and a company is never prepared twice, across campaigns.

## Quick start

As a Claude Code skill:

```bash
git clone https://github.com/jorgecTT/nosework ~/.claude/skills/nosework
```

Then tell your agent: *"prospect bakeries in Miami-Dade for me"*. The first time, it interviews you (what you sell, who buys, where, sender, opt-out, postal address) and writes your own profile.

With any other agent, or by hand:

```bash
git clone https://github.com/jorgecTT/nosework && cd nosework
python3 scripts/doctor.py                      # checks python, internet, OpenStreetMap, optional Brave key
cp .env.example .env                           # optional: BRAVE_API_KEY for web search
python3 scripts/prospect.py --campaign demo --state FL --counties "Miami-Dade County" --sectors food --max 30
```

The run pauses at the draft step so the agent can write the first lines (see `SKILL.md`), then:

```bash
python3 scripts/prospect.py --campaign demo --from draft
```

> **OpenStreetMap down?** The free Overpass servers are volunteer-run and often overloaded. nosework tries four mirrors, and you can set `NOSEWORK_OVERPASS` to your own. With a free Brave Search key in `.env` it still finds companies when OpenStreetMap is unavailable (`--source brave`).

## Make it yours

Everything about your business lives in a profile folder: offer, sectors, signals, signature, opt-out, banned phrases, exclusions.

```
profiles/
  example-translation-agency/   a complete, fictional worked example (Acme Translations)
  _template/                    blank, with every key explained
```

Pick one with `--profile profiles/<name>` or `export NOSEWORK_PROFILE=<name>`. See `docs/PROFILES.md` and `docs/REGIONS.md` (adding any state, county or country).

## Use it responsibly

nosework helps you find businesses that publish a contact address. You are responsible for how you use it: honor opt-outs, include your physical address, follow CAN-SPAM, CASL, GDPR/PECR or your local rules, and never send to people who asked you to stop. Read `docs/COMPLIANCE.md` first. It refuses to use LinkedIn, Google Maps or Yelp as sources, ignores pages `robots.txt` disallows, and never skips a captcha.

## Layout

```
SKILL.md       instructions for the agent
scripts/       the 7 steps and helpers (stdlib only)
profiles/      example and template
references/    regions, role mailboxes, disposable domains, rules, templates
docs/          compliance, profiles, regions
tests/         python3 -m unittest discover -s tests
data/          your campaigns and contacts (git-ignored)
```

## Contributing

Issues and PRs are welcome: new regions, sector profiles for other industries, better signals, more registry lookups. Keep it standard-library only, keep tests green, and keep example data fictional.

## Credits

Ideas and data reused with their licenses:

- [reacherhq/check-if-email-exists](https://github.com/reacherhq/check-if-email-exists) (MIT): checking that a domain receives mail without sending anything, and the role mailbox list.
- [scrapinghub/extruct](https://github.com/scrapinghub/extruct) (BSD): reading the data a company declares for search engines (schema.org).
- [disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains) (CC0): `references/disposable-domains.txt`.
- OpenStreetMap contributors (ODbL) through the Overpass API.

## License

MIT, see `LICENSE`.
