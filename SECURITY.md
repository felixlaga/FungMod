# Security Policy

## Supported Versions

FungMod is released from a single active line. Security fixes are applied to the
latest released version on PyPI and to the `main` branch. Older versions are not
maintained.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report vulnerabilities privately through GitHub's coordinated disclosure tools:

1. Go to <https://github.com/felixlaga/FungMod/security/advisories/new>.
2. Describe the vulnerability, the affected version(s), and, if possible, a
   minimal reproduction.

If you cannot use GitHub Security Advisories, email the maintainer at
felix.laga@yahoo.com with the subject line `FungMod security report`.

### What to expect

- **Acknowledgement** within 5 business days.
- **An initial assessment** (severity, affected versions, remediation plan)
  within 10 business days.
- **Coordinated disclosure**: we will agree on a disclosure timeline with you
  and credit you in the release notes unless you prefer to remain anonymous.

## Scope

FungMod is a scientific modelling library. The most relevant security surfaces
are:

- **Untrusted configuration and registry files** (`.yml`/`.json`) loaded through
  the public API. FungMod parses these with `yaml.safe_load` and validates
  schemas, but you should still treat model/registry files from untrusted
  sources with caution.
- **Curator signature verification** (`fungmod.sign_curation_bundle`,
  `load_authenticated_curation_bundle`). Report any bypass of signature
  verification or trust-anchor handling.
- **Deserialization of simulation outputs and manifests.**

Reports about denial-of-service from deliberately pathological inputs (for
example, configurations that request extremely large grids) are welcome but are
generally treated as robustness bugs rather than vulnerabilities.
