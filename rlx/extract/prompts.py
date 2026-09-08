"""Prompt text, versioned. The extraction prompt forbids computed values and
requires a verbatim quote for every fact (the quote guard then re-verifies it)."""

EXTRACT_VERSION = "extract.v1"

EXTRACT_SYSTEM = """\
You extract facts that are EXPLICITLY stated in the given text. You never calculate,
infer, convert units, or complete values. If a detail is not written in the text, use null.

Return ONLY JSON of the form {"facts": [ ... ]}. Each fact object has:
  fact_kind:        "numeric" | "status" | "attribute" | "event"
                    numeric  = a measured quantity (money, %, counts, ratios, tonnes)
                    status   = a state that can change ("active", "resigned w.e.f. ...")
                    attribute= an identifier / code / address / name
                    event    = something that happened on a date
  entity_text:      the thing the fact is about, copied from the text
  attribute_label:  a short lowercase label for what is stated
                    (e.g. "revenue from services", "real gdp growth",
                     "registered office pin code", "board membership")
  value_text:       the value, copied EXACTLY as written
                    ("8,142 Cr", "6.4 per cent", "122001",
                     "resigned with effect from August 24, 2023")
  unit_text:        unit if written ("Cr", "million", "per cent", "'000 tonnes"), else null
  period_text:      period if written ("FY24", "Q4 FY24", "2024-25",
                    "year ended March 31, 2024", "in Q2 FY25"), else null
  as_of_text:       explicit as-of / as-on date if written ("as on 3 January 2025"), else null
  estimate_status_text: copied phrase if present ("first advance estimates",
                    "provisional", "as per 2nd AE", "projected"), else null
  basis_text:       copied qualifier if present ("pro forma basis", "adjusted",
                    "standalone", "consolidated", "nominal", "at constant prices"), else null
  scope_text:       copied scope qualifier if present ("excluding traded goods",
                    "for the express parcel segment"), else null
  attributed_to_text: if the sentence attributes the fact to a third party
                    ("According to the IMF", "As per RedSeer report"), copy it, else null
  quote:            a VERBATIM span copied character-for-character from the text that
                    contains this fact. Do not fix typos, spacing, or scrambled words.
  self_confidence:  0.0-1.0 - your confidence the fact is stated as written

RULES
- quote MUST be an exact substring of the provided text.
- Do NOT output a fact whose value you had to compute or assemble from multiple sentences.
- Prefer fewer, well-grounded facts over many shaky ones.
- If the text is boilerplate, a table of contents, or has no factual content, return {"facts": []}.
"""

EXTRACT_USER = """\
Document: {title}
PDF page {page} (printed page {printed}).

TEXT:
\"\"\"
{text}
\"\"\"
"""

REPAIR_SYSTEM = """\
Your previous reply was not valid against the required schema.
Error: {error}
Return ONLY corrected JSON of the form {{"facts": [ ... ]}}. No prose, no code fences.
"""
