# Security Policy

## Scope

This project is a local Python framework for simulating virtual CPU schedulers and analyzing their behavior. Security concerns include, in particular:

- vulnerabilities in third-party Python dependencies;
- unsafe handling of configuration, input files, or generated outputs;
- accidental exposure of credentials, tokens, or other sensitive information;
- code changes that could execute unintended commands or access data outside the project.

The simulator is not intended to provide isolation or security guarantees for production workloads. Its scheduling behavior and evaluation results should not be used as a substitute for security controls in a hypervisor or operating system.

## Supported versions

| Version or branch         | Support     |
| ------------------------- | ----------- |
| `main` (development head) | Supported   |
| Tagged releases           | Best effort |

Security fixes are developed against the current `main` branch whenever possible. Users of older revisions should upgrade to the latest available revision before requesting a fix.

## Reporting a vulnerability

Please do not disclose security vulnerabilities in a public issue, pull request, discussion, or README link.

Use the private vulnerability reporting or security advisory feature provided by the repository host. Include, when possible:

- a short summary and the affected file, component, dependency, or configuration;
- the project version or revision, Python version, and operating system;
- the affected usage context, such as local simulation, shared workstation, or generated output;
- precise reproduction steps or a minimal proof of concept;
- the potential impact and any suggested mitigation or fix.

If the repository host does not provide a private reporting channel, contact the project maintainers through an official private channel associated with the repository. Do not include passwords, access tokens, personal data, or other secrets in the report.

Reports should be limited to non-sensitive routing details until a private channel has been confirmed. Do not share exploit code, secrets, detailed proof-of-concept material, or sensitive logs in a public location. Please allow maintainers reasonable time to investigate and prepare a fix before publicly disclosing the vulnerability.

Public issues remain appropriate for non-sensitive bugs, support questions, and post-fix follow-up. They are not vulnerability intake channels.

## Coordinated disclosure

For a confirmed vulnerability, maintainers will:

1. acknowledge and assess the report;
2. work with the reporter to understand the affected code and impact;
3. prepare a remediation or mitigation when appropriate;
4. release the fix and publish security notes when disclosure is appropriate.

Reporter credit will be given only with permission. Critical or actively exploited issues may be handled outside the normal development cadence.

## Security release process

Maintainers triage reports according to exploitability, impact, affected usage, and available mitigations. Remediation may include a code change, dependency update, configuration guidance, or a documented limitation.

When appropriate, a security advisory will describe the impact, affected versions or revisions, fixed versions or revisions, and upgrade or mitigation instructions. CVE or other advisory identifiers may be included when available.

## Dependency security

Dependencies are pinned in `requirements.txt` and should be reviewed before updates are merged. Run a dependency audit when investigating or changing dependencies:

```bash
pip-audit -r requirements.txt
```

Dependency changes should explain the reason for the update and any relevant security impact. Do not commit local virtual environments, generated credentials, secret files, or machine-specific configuration.

## Adoption and hardening guidance

This project is intended for trusted-operator, local research and evaluation use. It is not a sandbox for untrusted Python code, workloads, configuration, dependencies, or generated files. Do not treat the simulator as a security boundary.

For shared or sensitive environments:

- run the project in an isolated virtual environment or disposable workspace;
- review scheduler configurations, dependencies, and generated outputs before execution or sharing;
- keep credentials, private datasets, and machine-specific settings outside the repository;
- restrict filesystem and network access according to the deployment threat model;
- use appropriate operating-system, container, or virtual-machine isolation for untrusted workloads;
- retain dependency-audit results for the actual environment being deployed.

## Secure contribution practices

Contributors should:

- validate configuration values before using them in new code;
- avoid shell commands built from untrusted or unsanitized input;
- keep generated simulation data separate from source-controlled code;
- remove sensitive information from logs, screenshots, and issue or pull request descriptions;
- report suspected vulnerabilities privately rather than opening a public issue.

For general bugs and non-sensitive improvements, use the process described in [CONTRIBUTING.md](CONTRIBUTING.md).
