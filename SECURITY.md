# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities privately using
[GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability):
go to the **Security** tab of this repository and select **Report a vulnerability**.

Do not open a public issue for a security vulnerability.

We aim to acknowledge reports within 5 business days.

## Scope

**In scope:**
- The Recwise codebase itself (parsing, matching, export, CLI).
- The synthetic data generator (`recwise.synth`).
- Build, CI, and pre-commit configuration in this repository.

**Out of scope:**
- Vulnerabilities in third-party dependencies — please report those upstream
  (though we'd still appreciate a heads-up so we can update our pin).
- Social engineering, physical security, or issues requiring access to a
  user's own machine that Recwise itself does not create.

## Offline by design

Recwise is built to run entirely offline. It makes no network calls, has no
telemetry, no analytics, and no update-check mechanism. It never sends your
financial data anywhere. If you find code that contacts the network, that is
itself a bug worth reporting under this policy.
