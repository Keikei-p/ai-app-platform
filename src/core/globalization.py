from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class LocaleProfile:
    language: str
    region: str
    timezone: str
    currency: str
    date_format: str

LOCALE_PRESETS = {
    "ja-JP": LocaleProfile("ja", "JP", "Asia/Tokyo", "JPY", "YYYY-MM-DD"),
    "en-US": LocaleProfile("en", "US", "America/New_York", "USD", "MM/DD/YYYY"),
    "en-GB": LocaleProfile("en", "GB", "Europe/London", "GBP", "DD/MM/YYYY"),
    "de-DE": LocaleProfile("de", "DE", "Europe/Berlin", "EUR", "DD.MM.YYYY"),
}
SUPPORTED_UI_LANGUAGES = ["ja", "en"]

@dataclass(frozen=True)
class RegionComplianceHint:
    region: str
    checks: list[str]

REGION_HINTS = {
    "JP": RegionComplianceHint("JP", ["privacy_policy", "consumer_terms", "commercial_transaction_disclosure_if_applicable"]),
    "US": RegionComplianceHint("US", ["privacy_policy", "state_privacy_review_if_applicable"]),
    "EU": RegionComplianceHint("EU", ["privacy_policy", "lawful_basis", "data_subject_rights", "cookie_consent_if_applicable"]),
}
