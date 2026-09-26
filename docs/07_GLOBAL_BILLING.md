# Globalization & Billing

## Globalization

Platform-level profile contains:

- language
- country/region
- timezone
- currency
- date/time format
- tax display preference
- store/publication region
- data residency preference (where supported)

Translation packs must be separate from business logic.

## Billing core

Billing state is internal and provider-neutral:

- customer
- plan
- subscription state
- entitlement
- usage meter
- invoice reference
- trial
- coupon/promotion
- refund/credit reference

Payment execution is delegated to adapters.

## Proposed plan structure

### Free
Explore/local projects, limited automation.

### Personal
Home PC Worker, personal projects, more automation.

### Pro
Higher limits, multiple apps, advanced maintenance.

### Cloud
Hosted Worker for PC-less/mobile-only users; metered compute.

### Business
Teams, roles, multiple workers, audit/admin controls.

### Enterprise
Enterprise Worker/BYOC, policy controls, dedicated support/compliance options.

## Cost protection

- Hard usage limits
- Budget alerts
- User-set spending cap
- Preflight cost estimate for heavy jobs
- Hosted Worker auto-stop
- No autonomous plan upgrade or spending-limit change
