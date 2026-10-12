#!/usr/bin/env python3
"""AICC Engineering Toolkit — shared TLS context + certificate diagnostics.

Every Workbench HTTPS request (registration, lifecycle sync, evidence submit)
builds its SSL context here, so trust and verification policy are defined in ONE
place and are identical across clients.

------------------------------------------------------------------------------
WHY THIS EXISTS — corporate SSL inspection (Netskope/Zscaler/etc.)
------------------------------------------------------------------------------
Python 3.13+ turns on ssl.VERIFY_X509_STRICT by default in
ssl.create_default_context(). Strict mode enforces RFC 5280, which requires
every CA certificate in the chain to carry a Key Usage extension with
keyCertSign (and cRLSign). A TLS-inspection proxy that injects a root CA
*without* that extension therefore fails verification on Python 3.13+ with:

    [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
    CA cert does not include key usage extension

Python <= 3.12, curl, and browsers do NOT enforce this, which is why the same
host works everywhere else. On Windows, create_default_context() already loads
the Windows system trust stores, so the proxy CA is normally FOUND (the chain
builds) — the failure is the structural Key Usage rule, not an unknown CA.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES — and does NOT do
------------------------------------------------------------------------------
build_ssl_context() returns a context that ALWAYS:
  - verifies the full certificate chain (verify_mode = CERT_REQUIRED),
  - verifies the hostname (check_hostname = True),
  - uses the platform's default trust store (incl. the Windows cert store).

It NEVER disables verification. There is no verify=False, no CERT_NONE, no
hostname bypass, no proxy bypass.

The ONLY policy knob is a narrow, explicit, opt-in relaxation of the
VERIFY_X509_STRICT flag — and ONLY that flag — which restores the exact
Python <= 3.12 behavior for the Key Usage rule while leaving chain, hostname,
expiry, and basic-constraints checks fully intact. It is OFF by default and must
be turned on deliberately (CLI flag / env var) by an engineer who understands
their corporate proxy CA is non-compliant and cannot yet be re-issued.

diagnose_tls_error() classifies a verification failure so the installer can tell
the engineer precisely which of these it is, and hand them an IT-ready
remediation request instead of silently weakening security.

Stdlib only.
"""
from __future__ import annotations

import ssl

# Explicit opt-in to relax ONLY the strict Key Usage rule. Default: off.
RELAX_KEYUSAGE_ENV = "AICC_TLS_RELAX_KEYUSAGE"

# Diagnostic classifications.
TLS_OK = "OK"
TLS_UNKNOWN_CA = "UNKNOWN_CA"            # trust anchor not found
TLS_INVALID_CA_KEYUSAGE = "INVALID_CA_KEYUSAGE"  # CA present but structurally non-compliant
TLS_REVOCATION = "REVOCATION"            # revocation check failed
TLS_PROXY_NETWORK = "PROXY_NETWORK"      # could not establish the connection
TLS_OTHER_VERIFY = "OTHER_VERIFY"        # some other verification failure


def strict_available() -> bool:
    """True if this Python exposes VERIFY_X509_STRICT (3.13+)."""
    return hasattr(ssl, "VERIFY_X509_STRICT")


def build_ssl_context(relax_keyusage: bool = False) -> ssl.SSLContext:
    """Build the shared verifying TLS context.

    chain + hostname verification are ALWAYS on and the platform trust store
    (including the Windows system store) is used. When relax_keyusage is True
    AND this Python supports strict mode, ONLY the VERIFY_X509_STRICT flag is
    cleared — restoring Python <= 3.12 behavior for the Key Usage rule. Nothing
    else is weakened.
    """
    ctx = ssl.create_default_context()
    # Defensive: guarantee verification is on regardless of defaults.
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    if relax_keyusage and strict_available():
        # Clear ONLY the strict flag; keep every other verification rule.
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def relax_requested(explicit: bool | None, env: dict | None = None) -> bool:
    """Resolve whether the strict-flag relaxation is requested.

    Precedence: explicit CLI flag (if not None) > env var > False.
    The env var is truthy for '1', 'true', 'yes' (case-insensitive).
    """
    if explicit is not None:
        return bool(explicit)
    import os
    environ = os.environ if env is None else env
    val = (environ.get(RELAX_KEYUSAGE_ENV) or "").strip().lower()
    return val in ("1", "true", "yes", "on")


def diagnose_tls_error(exc: BaseException) -> tuple[str, str]:
    """Classify a TLS/connection failure. Returns (code, human_message).

    Distinguishes: unknown CA, invalid CA Key Usage, revocation failure, and
    proxy/network failure, so the caller never conflates 'not trusted' with
    'structurally invalid'.
    """
    # Reach the most specific cause.
    verify_msg = ""
    cur: BaseException | None = exc
    seen = 0
    while cur is not None and seen < 10:
        if isinstance(cur, ssl.SSLCertVerificationError):
            verify_msg = (getattr(cur, "verify_message", "") or str(cur)).lower()
            break
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
        seen += 1
    text = (verify_msg or str(exc)).lower()

    if "key usage" in text:
        return (TLS_INVALID_CA_KEYUSAGE, _keyusage_report())
    if "unable to get local issuer" in text or "self-signed certificate" in text \
            or "self signed certificate" in text or "unable to get issuer" in text:
        return (TLS_UNKNOWN_CA,
                "The server's certificate chain is not trusted by this machine (unknown CA). "
                "Behind a corporate SSL-inspection proxy, the proxy's root CA must be installed "
                "in the OS trust store (Windows: Trusted Root Certification Authorities). Ask IT "
                "to deploy the inspection root CA to this machine's system trust store, then retry.")
    if "revoc" in text or "crl" in text or "ocsp" in text:
        return (TLS_REVOCATION,
                "Certificate revocation checking failed or returned warnings. This is usually a "
                "transient or proxy-related CRL/OCSP reachability problem; retry, and if it "
                "persists ask IT whether CRL/OCSP endpoints are reachable through the proxy.")
    if isinstance(exc, ssl.SSLCertVerificationError) or "certificate verify failed" in text:
        return (TLS_OTHER_VERIFY,
                f"Certificate verification failed: {verify_msg or str(exc)}. Verification was NOT "
                "weakened. If this is a corporate proxy CA problem, share the finding with IT.")
    # Non-TLS connection problems (DNS, refused, timeout, proxy tunnel).
    return (TLS_PROXY_NETWORK,
            f"Could not establish a TLS connection: {exc}. Common corporate causes: outbound "
            "HTTPS blocked, a proxy that needs HTTPS_PROXY/HTTP_PROXY set, or DNS filtering. "
            "Confirm proxy settings with IT and retry.")


def _keyusage_report() -> str:
    """Precise finding + IT-ready remediation for the Key Usage case."""
    relax_hint = ""
    if strict_available():
        relax_hint = (
            "\n\nIf IT cannot re-issue the CA immediately, an engineer who accepts the risk may "
            "re-run with --allow-legacy-tls-keyusage (or set %s=1). That relaxes ONLY the strict "
            "Key Usage rule — chain, hostname, and expiry verification stay fully enforced — "
            "matching Python 3.12 behavior. It is OFF by default." % RELAX_KEYUSAGE_ENV
        )
    return (
        "The TLS certificate presented for the Workbench host was issued by your corporate "
        "SSL-inspection proxy's root CA, and that CA certificate is STRUCTURALLY NON-COMPLIANT: "
        "it is missing the X.509v3 Key Usage extension that RFC 5280 requires on a CA certificate. "
        "Python 3.13+ enforces this (VERIFY_X509_STRICT); the chain is otherwise trusted and builds "
        "successfully. This is NOT an 'untrusted CA' problem and installing additional CA bundles "
        "(e.g. certifi) will NOT fix it.\n\n"
        "IT remediation request (recommended, permanent fix):\n"
        "  Re-issue the SSL-inspection (Netskope) root/intermediate CA certificate with:\n"
        "      X509v3 Basic Constraints: critical, CA:TRUE\n"
        "      X509v3 Key Usage:         critical, Certificate Sign, CRL Sign\n"
        "  and redeploy it to this machine's Trusted Root Certification Authorities store."
        + relax_hint
    )
