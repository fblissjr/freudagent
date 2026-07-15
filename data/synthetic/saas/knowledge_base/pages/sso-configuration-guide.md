---
page_id: KB-127
space: product-docs
title: SSO configuration guide (SAML)
author: marcus.webb
created: 2025-12-10
last_updated: 2026-04-11
version: 4
labels: [auth, sso, enterprise]
---

# SSO configuration guide (SAML)

SAML single sign-on is available on scale and enterprise plans. Group-based
role mapping is enterprise-only.

## Setup

1. In **Admin → Authentication**, download the service-provider metadata.
2. Create the application in your identity provider and upload our metadata.
3. Paste your IdP metadata URL back into the Acme admin panel.
4. Assign test users and verify login before enforcing SSO org-wide.

## Group-based role mapping

Map identity-provider groups to Acme roles (`viewer`, `editor`, `admin`)
under **Admin → Authentication → Role mapping**. First match wins; users
with no matching group get the org default role.

The groups attribute must be sent as a multi-value SAML attribute named
`groups`.

> **Known issue (2026-04):** assertions where the IdP chunks a large groups
> list across multiple `AttributeValue` elements (commonly seen above ~20
> groups) can fail role mapping with an `assertion invalid` error. A fix is
> in progress; the interim workaround is to filter the groups claim at the
> IdP to only the groups used in role mapping. Reference support ticket
> SUP-1057 when escalating.

## Enforcement

Once verified, enable **Require SSO**. Break-glass admin accounts with
hardware-key MFA remain able to log in with a password; all other password
logins are disabled.
