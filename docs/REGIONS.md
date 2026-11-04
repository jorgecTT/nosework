# Regions

`references/regions.json` lists the states (or any region) nosework can search, with the counties to work in
order. **The shipped entries (FL, TX, NY) are sample data.** Add your own.

## Add a state, county or country

1. Copy an entry under `"states"` and rename its key. The key is what you pass as `--state`.
2. Set `"name"` to the text a company's site must mention to count as being there (for example "Ohio").
3. Set `"iso"` to the ISO 3166-2 code that OpenStreetMap uses for the area, for example `US-OH`, `CA-ON`, `GB-ENG`,
   `MX-JAL`. You can check it on the OpenStreetMap wiki or with the Overpass turbo query
   `area["ISO3166-2"="US-OH"];out;`.
4. List the areas to search in `"counties"`. Each entry has `"county"` (the exact name OpenStreetMap has for the
   area) and `"cities"` (used for web searches with Brave). The sample uses US counties (OpenStreetMap
   `admin_level` 6). For another country set `"admin_level"` on the state to the level that matches (for
   example `"4"` for Canadian provinces or German states, `"8"` for French communes) and use that level's names.
5. Order matters: `coverage.py` recommends the next search following the file order.

For a place with a different language, add the language to your profile's `locales`, `signals.json` terms and
`variants.json` (see `docs/PROFILES.md`).

## Optional registry lookups (step 3)

`scripts/registry.py` can estimate a company's age from a state's open business registry. It is **off by
default**; run it with `python3 scripts/prospect.py ... --registry` or on its own. It is a bonus, never a
requirement, and every lookup fails soft (an error is recorded in `registry.jsonl` and ignored).

| `registry` value | What it reads |
|---|---|
| `fl_sunbiz_local` | Sunbiz daily filing files that you downloaded yourself into `data/sunbiz/*c.txt` (only recent filings, so a match means "new company") |
| `tx_franchise` | Texas Comptroller franchise tax permit holders on data.texas.gov (Socrata API) |
| `ny_corporations` | NY Department of State active corporations on data.ny.gov (Socrata API) |

These open-data endpoints can change or throttle; if one breaks, ignore the step. Business names on websites
often differ from legal names, so many companies will not match, and that is normal. To add another registry,
write a lookup function in `registry.py` and a branch in `lookup`.
