# Runbook: laptop provisioning and deprovisioning

- **Owner:** IT (Diego Fuentes); maintained by Lena Fischer and Omar Haddad
- **Audience:** IT Support and Systems Engineering
- **Last updated:** 2026-06-12

## When this runs

A new-hire record in **Fernwake People** automatically opens an onboarding
ticket in **Torchstone Desk**. Ticket titles follow the format:

> Onboarding: <Full Name> (EMP-####) - start <YYYY-MM-DD>

Work the ticket end to end; close it only when the machine and accounts are
ready and verified. SLA is **5 business days from ticket open to ready**, so
start on receipt, not on the start date.

## Hardware

- Pull hardware from **Corvid Hardware Supply** stock.
- Standard issue is the **Corvid Book 14**. Engineering may request the
  **Corvid Book 16**; note the request in the ticket.
- Before issuing, record the **asset tag** (`AST-####`) and the serial number
  in the asset register. No machine leaves IT without a register entry --
  the register, not the ticket, is the source of truth for who holds what.

## Standard image

Every issued machine is built from the standard image with:

- Full-disk encryption **on** and verified.
- **Bramblehold VPN** client configured.
- **Glimmerfen Chat**.
- Managed browser with policy profile.
- **Nightledger** endpoint agent enrolled and reporting.

Confirm each item is present and healthy before handoff; a machine that is
not reporting to Nightledger is not ready.

## Account provisioning

- **SSO-first** via the app catalog. Provision accounts through SSO wherever
  the app supports it rather than standalone logins.
- Grant entitlements strictly per the **role matrix** for the new hire's
  role. Do not copy a peer's access ("make them like so-and-so") -- that is
  how entitlement creep starts.
- MFA is enrolled at setup; admin-eligible roles get hardware security keys.

## Loaner pool

IT keeps a small loaner pool for machines in repair or for short-term needs.
Loaners are tracked in the asset register like any other unit and returned to
the pool, wiped, when handed back.

## Break/fix and warranty

- Log hardware faults as a Torchstone Desk ticket against the asset tag.
- In-warranty repairs go through Corvid Hardware Supply; out-of-warranty
  units are assessed for repair vs. replacement by Systems Engineering.
- Issue a loaner if a repair will exceed one business day.

## Offboarding

The manager opens an **offboarding ticket in Torchstone Desk before the
employee's last day**. IT works the following checklist and does not close
the ticket until every item is confirmed:

- [ ] **Badge deactivated** in Doorstile.
- [ ] **Directory account disabled** (not deleted) at the effective time.
- [ ] **Laptop returned and wiped**; asset returns to stock and the register
      is updated.
- [ ] **Mail forwarding** configured per Legal's guidance for the role.
- [ ] **Per-app SaaS deprovisioning** against the app catalog: walk the
      catalog and revoke every entitlement individually, not just SSO.

> The per-app SaaS deprovisioning step was added in the **June 2026
> revision** after a Q2 access review found a terminated employee's Saltmarsh
> CRM entitlement still active. Disabling the directory account is not enough
> when an app grants access outside SSO -- each entitlement must be revoked
> explicitly.

## Reconciliation

IT reconciles the **asset register against Fernwake People quarterly**:
every active employee maps to their issued assets, every returned asset is
back in stock, and no account or entitlement outlives its owner. Discrepancies
open a Torchstone Desk ticket and are resolved before the review closes.
