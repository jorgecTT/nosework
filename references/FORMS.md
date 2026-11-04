# Companies that are reached through a form

Many companies publish no email but have a "Contact us" form. `scan.py` finds them and `export.py` writes
them to `data/<campaign>/FORMS_<campaign>.csv`. **nosework does not submit them.** The file is the input for
whatever you use to do it by hand or with your own tool.

## Columns

| Column | What it holds |
|---|---|
| `id` | The same kind of id as the queue (`L100000` and up) |
| `company`, `sector`, `city`, `state` | Who they are |
| `form_page` | The page where the form is |
| `action`, `method` | Where the form posts to (`post` or `get`), or `external` if embedded from another service |
| `fields` | The field names (`your-name your-email your-message`...) |
| `captcha` | `recaptcha`, `hcaptcha`, `turnstile` or empty |
| `provider` | `contact_form_7`, `gravity`, `wpforms`, `elementor`, `hubspot`, `jotform`, `typeform`, `wix`, `html`... |
| `message` | The ready-written text, which passed the verifier |

## If you automate it

- Forms **without a captcha** and with provider `html`, `contact_form_7`, `wpforms` or `gravity` are the easy ones.
- **A captcha is never bypassed.** Those are done by hand or not at all.
- `external` forms (HubSpot, JotForm, Typeform, Google Forms) are filled on the provider's page, with the same rules.
- Submitting a form is sending a message in your name: the same consent, opt-out and frequency rules as email
  apply (see `docs/COMPLIANCE.md`).
- After sending, record it with `python3 scripts/contacts.py mark <domain> sent` so you do not write again.
