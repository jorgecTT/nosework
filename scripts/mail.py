"""Checks on an email address that need no email to be sent (idea taken from reacherhq/check-if-email-exists).

  mail_domain(dom)  asks public DNS (DNS over HTTPS: Cloudflare, then Google) whether the domain can receive
                    mail at all: a domain that doesn't exist or has no mail server (no MX) is a sure bounce.
                    It can't tell whether one mailbox exists (the "address not found" bounces): that needs
                    talking to the company's mail server, which is never done here, because from a home
                    connection it is often blocked and looks like spam.
  is_disposable     the address is a throwaway mailbox (references/disposable-domains.txt, CC0).
  is_role           a generic inbox like info@ or sales@ (references/role-mailboxes.txt, MIT): still
                    usable, but a named person's address beats it.
"""
import functools
import os
import urllib.parse

from common import FREE_MAIL, ROOT, get_json

DOH = ['https://cloudflare-dns.com/dns-query', 'https://dns.google/resolve']


def _list(name: str) -> set[str]:
    path = ROOT / 'references' / name
    return {l.strip().lower() for l in path.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')}


DISPOSABLE = _list('disposable-domains.txt')
ROLES = _list('role-mailboxes.txt')


def _query(dom: str, rtype: str) -> dict | None:
    for url in DOH:
        try:
            return get_json(f'{url}?{urllib.parse.urlencode({"name": dom, "type": rtype})}',
                            headers={'Accept': 'application/dns-json'}, timeout=15)
        except Exception:
            continue
    return None


@functools.lru_cache(maxsize=4096)
def mail_domain(dom: str) -> tuple[bool | None, str]:
    """(True, '') can receive mail, (False, reason) it can't, (None, reason) DNS didn't answer: unknown,
    never counted as a failure."""
    dom = dom.lower().strip('.')
    if dom in FREE_MAIL:
        return True, ''
    if os.environ.get('NOSEWORK_SKIP_DNS'):  # tests and offline use: the DNS check is skipped, never counted as a failure
        return None, 'DNS check skipped (NOSEWORK_SKIP_DNS)'
    mx = _query(dom, 'MX')
    if mx is None:
        return None, 'DNS did not answer'
    if mx.get('Status') == 3:
        return False, 'the domain does not exist'
    answers = [a for a in mx.get('Answer', []) if a.get('type') == 15]
    if answers:
        if all(a.get('data', '').split()[-1:] in (['.'], []) for a in answers):  # "0 ." = null MX (RFC 7505)
            return False, 'the domain says it receives no mail (null MX)'
        return True, ''
    return False, 'the domain has no mail server (no MX record)'


def is_disposable(email: str) -> bool:
    return email.split('@')[-1].lower() in DISPOSABLE


def is_role(email: str) -> bool:
    local = email.split('@')[0].lower()
    return local in ROLES or local.rstrip('0123456789') in ROLES
