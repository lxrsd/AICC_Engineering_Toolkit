#!/usr/bin/env python3
"""Tests for the shared TLS context + certificate diagnostics (installer/tls.py).

Two layers:

  * UNIT — build_ssl_context() policy and diagnose_tls_error() classification,
    plus relax-precedence. No network.

  * REAL HANDSHAKE — reproduces the corporate SSL-inspection failure locally: a
    CA certificate issued WITHOUT the X.509 Key Usage extension (exactly the
    Netskope/Zscaler case). It proves:
      1. the strict default context REJECTS it with the reported
         'CA cert does not include key usage extension' error,
      2. the opt-in relaxed context ACCEPTS it,
      3. the relaxed context STILL enforces hostname verification (a wrong
         hostname is rejected) — i.e. the relaxation narrows ONLY the Key Usage
         rule, never chain/hostname.
    These require the `openssl` CLI and run against a localhost socket; they are
    skipped (not failed) where openssl is unavailable, and are only meaningful
    on a Python that enables VERIFY_X509_STRICT (3.13+).

Run: python3 installer/test_tls.py
"""
from __future__ import annotations

import os
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest

import tls


class ContextPolicy(unittest.TestCase):
    def test_strict_context_fully_verifies(self):
        ctx = tls.build_ssl_context(relax_keyusage=False)
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        if tls.strict_available():
            self.assertTrue(ctx.verify_flags & ssl.VERIFY_X509_STRICT)

    def test_relaxed_context_keeps_chain_and_hostname(self):
        ctx = tls.build_ssl_context(relax_keyusage=True)
        self.assertTrue(ctx.check_hostname, "hostname verification must stay ON")
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED, "chain verification must stay ON")
        if tls.strict_available():
            self.assertFalse(ctx.verify_flags & ssl.VERIFY_X509_STRICT,
                             "only the strict Key Usage flag is cleared")

    def test_relax_precedence(self):
        self.assertTrue(tls.relax_requested(True, env={}))
        self.assertFalse(tls.relax_requested(False, env={"AICC_TLS_RELAX_KEYUSAGE": "1"}))
        self.assertTrue(tls.relax_requested(None, env={"AICC_TLS_RELAX_KEYUSAGE": "yes"}))
        self.assertFalse(tls.relax_requested(None, env={}))
        self.assertFalse(tls.relax_requested(None, env={"AICC_TLS_RELAX_KEYUSAGE": "0"}))


class Diagnostics(unittest.TestCase):
    def _verify_error(self, msg):
        e = ssl.SSLCertVerificationError(msg)
        e.verify_message = msg
        return e

    def test_keyusage_classified_with_remediation(self):
        code, report = tls.diagnose_tls_error(self._verify_error("CA cert does not include key usage extension"))
        self.assertEqual(code, tls.TLS_INVALID_CA_KEYUSAGE)
        self.assertIn("Key Usage", report)
        self.assertIn("Certificate Sign", report)   # IT-ready remediation
        self.assertIn("CRL Sign", report)
        self.assertIn("NOT an 'untrusted CA'", report)

    def test_unknown_ca_classified(self):
        code, report = tls.diagnose_tls_error(self._verify_error("unable to get local issuer certificate"))
        self.assertEqual(code, tls.TLS_UNKNOWN_CA)
        self.assertIn("trust store", report.lower())

    def test_revocation_classified(self):
        code, _ = tls.diagnose_tls_error(self._verify_error("unable to get certificate CRL"))
        self.assertEqual(code, tls.TLS_REVOCATION)

    def test_network_classified(self):
        import urllib.error
        code, _ = tls.diagnose_tls_error(urllib.error.URLError("Connection refused"))
        self.assertEqual(code, tls.TLS_PROXY_NETWORK)

    def test_wrapped_sslerror_is_unwrapped(self):
        inner = self._verify_error("CA cert does not include key usage extension")
        outer = OSError("tunnel failed")
        outer.__cause__ = inner
        code, _ = tls.diagnose_tls_error(outer)
        self.assertEqual(code, tls.TLS_INVALID_CA_KEYUSAGE)


def _have_openssl():
    try:
        subprocess.run(["openssl", "version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


@unittest.skipUnless(_have_openssl(), "openssl CLI not available")
@unittest.skipUnless(tls.strict_available(), "Python without VERIFY_X509_STRICT (<3.13): not affected")
class RealHandshakeKeyUsage(unittest.TestCase):
    """Reproduce the Netskope-style non-compliant CA locally and prove the fix."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.ca_key = os.path.join(cls.dir, "ca.key")
        cls.ca_cert = os.path.join(cls.dir, "ca.pem")
        cls.srv_key = os.path.join(cls.dir, "srv.key")
        cls.srv_csr = os.path.join(cls.dir, "srv.csr")
        cls.srv_cert = os.path.join(cls.dir, "srv.pem")

        def ssl_cli(*args, stdin=None):
            r = subprocess.run(["openssl", *args], input=stdin, capture_output=True)
            if r.returncode != 0:
                raise unittest.SkipTest(f"openssl failed: {r.stderr.decode()[:200]}")

        # CA WITHOUT keyUsage — mimics the broken SSL-inspection root CA.
        ssl_cli("req", "-x509", "-newkey", "rsa:2048", "-keyout", cls.ca_key, "-out", cls.ca_cert,
                "-days", "1", "-nodes", "-subj", "/CN=AICC Test Inspection CA",
                "-addext", "basicConstraints=critical,CA:TRUE")
        # Server cert for localhost signed by that CA.
        ssl_cli("req", "-newkey", "rsa:2048", "-keyout", cls.srv_key, "-out", cls.srv_csr,
                "-nodes", "-subj", "/CN=localhost")
        ssl_cli("x509", "-req", "-in", cls.srv_csr, "-CA", cls.ca_cert, "-CAkey", cls.ca_key,
                "-CAcreateserial", "-out", cls.srv_cert, "-days", "1",
                "-extfile", "/dev/stdin", stdin=b"subjectAltName=DNS:localhost")

    def _handshake(self, ctx, server_hostname):
        """Open a localhost TLS server with the bad-CA cert and connect with ctx."""
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(self.srv_cert, self.srv_key)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.listen(1)

        def accept():
            try:
                conn, _ = srv.accept()
                try:
                    server_ctx.wrap_socket(conn, server_side=True).close()
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                srv.close()

        t = threading.Thread(target=accept)
        t.start()
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
                with ctx.wrap_socket(s, server_hostname=server_hostname):
                    pass
            return None
        except Exception as exc:
            return exc
        finally:
            t.join(timeout=5)

    def test_strict_rejects_keyusage_missing_ca(self):
        ctx = tls.build_ssl_context(relax_keyusage=False)
        ctx.load_verify_locations(cafile=self.ca_cert)
        exc = self._handshake(ctx, "localhost")
        self.assertIsNotNone(exc, "strict context must reject the non-compliant CA")
        code, _ = tls.diagnose_tls_error(exc)
        self.assertEqual(code, tls.TLS_INVALID_CA_KEYUSAGE)

    def test_relaxed_accepts_keyusage_missing_ca(self):
        ctx = tls.build_ssl_context(relax_keyusage=True)
        ctx.load_verify_locations(cafile=self.ca_cert)
        exc = self._handshake(ctx, "localhost")
        self.assertIsNone(exc, f"relaxed context should accept the chain, got: {exc!r}")

    def test_relaxed_still_enforces_hostname(self):
        # Relaxation must NOT weaken hostname verification: a wrong name fails.
        ctx = tls.build_ssl_context(relax_keyusage=True)
        ctx.load_verify_locations(cafile=self.ca_cert)
        exc = self._handshake(ctx, "wrong.example.test")
        self.assertIsNotNone(exc, "hostname verification must still reject a mismatched name")


if __name__ == "__main__":
    unittest.main(verbosity=2)
