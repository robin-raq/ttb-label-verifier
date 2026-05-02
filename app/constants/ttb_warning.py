"""Canonical TTB Government Health Warning per 27 CFR §16.21.

Source of truth (eyeball-verify before merge):
  https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16

The byte-perfect text below is what `app.comparators.warning_match` compares
against after whitespace normalization (SPEC §5.3, FR-005). ANY change here
is a behavioural change and SHALL trigger a SPEC version bump per the
Document Control / Schema evolution rules.

TODO(human): verify this string letter-for-letter against the live eCFR
URL above before kicking off Phase B. The model cannot judge whether the
text is correct; only the human can.
"""

CANONICAL_WARNING: str = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health problems."
)
