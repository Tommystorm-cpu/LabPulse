# Security

LabPulse runs close to laboratory hardware and can contain phone numbers,
network details and Home Assistant state. Please avoid sharing any of those in
a public issue, discussion or pull request.

## Reporting a vulnerability

Report a suspected vulnerability privately through
[GitHub's private vulnerability reporting page](https://github.com/lairdgrouplancaster/LabPulse/security/advisories/new).
Include the affected LabPulse version, the part of the system involved, the
impact you expect, and enough detail for a maintainer to reproduce the problem.
Please do not include real credentials or personal phone numbers unless a
maintainer has agreed a safe way to transfer them.

If private vulnerability reporting is unavailable, contact a Laird Group
repository owner through Lancaster University rather than opening a public
security issue.

Ordinary installation problems, documentation corrections and feature requests
can still use the public
[issue tracker](https://github.com/lairdgrouplancaster/LabPulse/issues).

## Supported releases

Security fixes are made against the latest published LabPulse release. Upgrade
to the latest release before reporting a problem which may already have been
fixed. Older releases may be used to reproduce an issue, but they do not receive
separate long-term support.

## Deployment boundary

The standard deployment assumes a trusted private laboratory network. Its local
MQTT listener must not be exposed directly to the public internet. Remote
publishers require authentication, TLS and network controls as described in the
relevant integration guide.

LabPulse is a monitoring aid, not a safety interlock or guaranteed alerting
channel. A security report does not replace independent protection for critical
equipment.
