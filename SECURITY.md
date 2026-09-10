# Security policy

## Project status

This repository is an **experimental prototype**. It is not a live service, it holds no production
data, and it is not supported or monitored as a production system. Please treat it accordingly when
reporting.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues, discussions or pull
requests.** Public reports give attackers the same information as the maintainers.

Report vulnerabilities through the GOV.UK vulnerability disclosure process:

**https://www.gov.uk/help/report-vulnerability**

Reports are submitted via HackerOne. GOV.UK aims to acknowledge a report within 5 working days and
to assess it within 10 working days. No bounty is offered.

Please include:

- the file, component or URL affected
- the type of vulnerability
- steps to reproduce
- any supporting logs or screenshots

## Guidance for researchers

When investigating, please do not:

- break the law
- access, modify or delete more data than is necessary to demonstrate the issue
- use high-intensity, invasive or destructive scanning tools
- attempt denial-of-service, social engineering, phishing or physical attacks
- disclose the issue publicly before it has been resolved

## Secrets in this repository

This repository is intended to contain **no credentials of any kind**. Secrets are held in AWS
Secrets Manager and injected at runtime — see `agent/app/secrets_manager.py`.

If you believe a credential has been committed here, please report it through the route above rather
than opening an issue. Per
[GOV.UK guidance](https://www.gov.uk/government/publications/open-source-guidance/security-considerations-when-coding-in-the-open),
any secret that reaches a public repository must be treated as compromised and rotated immediately,
however quickly it is removed.
