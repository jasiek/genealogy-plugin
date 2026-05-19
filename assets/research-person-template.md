<!--
Person note template. Copy to persons/<Firstname>_<Lastname>_<ID>.md and
fill in. Convention:
  - <ID> is the Heredis CodeID (or GEDCOM xref if no Heredis).
  - {{double-braces}} mark placeholders to replace.
  - [[bracketed]] links use the persons/<Firstname>_<Lastname>_<ID> slug
    (without the .md extension). Use a pipe alias for the display name,
    e.g. [[Józef_Pajor_31587|Józef Pajor]].
  - Drop sections that don't apply, but keep their order.
  - Dates: prefer ISO (YYYY-MM-DD) in tables; prose can be natural.
-->
---
aliases:
  - {{Given Name}} {{Surname}} ({{birth year}})
  - Heredis:{{code_id}}
  # - GEDCOM:{{gedcom_xref}}                # if a GEDCOM is the source
  # - {{Married Surname}}                   # add one alias per married surname
tags:
  - person
  - surname/{{Surname}}
  # - surname/{{MarriedSurname}}            # one tag per married surname
  - place/{{Primary place}}
  # - place/{{Parish or secondary place}}
---

# {{Given Name}} {{Surname}} ({{birth year}}–{{death year or ?}})

{{One- or two-sentence prose summary. State birth date/place, parents (linked),
key marriages (linked), notable life events, and death. This is the only prose
in the file; everything below is structured.}}

## Research Journal

<!-- One subsection per research session, newest at the bottom or top — pick one
     and be consistent across files. Bullet what was checked, what was found,
     and what was ruled out. Cite tools by name (heredis_get_family,
     geneteka_search, etc.) so future sessions can reproduce. -->

### [[{{YYYY-MM-DD}}]]

- {{What you pulled from the source of truth (Heredis / GEDCOM) and what it established.}}
- Searched Geneteka **{{region name}}** (`{{region code}}`), parish {{parish}}:
  - **{{record type, year range}}** `{{query}}` → {{N hits, summary, gid links}}.
  - **{{record type, year range}}** `{{query}}` → {{result}}.
- {{Other sources checked (Genealogia w Archiwach, GenPod, GenBaza, Lubgens, FamilySearch, archives, etc.) and outcome.}}
- {{Any data discrepancies, transcription doubts, or open threads spotted this session.}}

## Facts

<!-- One row per established fact. Every row MUST link to a source (Heredis
     CodeID, Geneteka gid URL, scan URL, headstone photo, etc.). If a fact
     is inferred or disputed, mark it **(inferred)** / **(disputed)** in the
     Event column and explain in Notes. -->

| Date | Event | Place | Source |
|------|-------|-------|--------|
| {{YYYY-MM-DD}} | {{Birth / Baptism}} | {{place, parish}} | {{Heredis CodeID …; Geneteka [act N/year, parafia X, gid=…](…)}} |
| {{YYYY-MM-DD}} | Marriage to [[{{Spouse_Slug}}\|{{Spouse display name}}]] | {{place}} | {{source link}} |
| {{YYYY-MM-DD}} | {{Child}} [[{{Child_Slug}}\|{{Child name}}]] born | {{place}} | {{source}} |
| {{YYYY-MM-DD}} | {{Death / Burial}} | {{place}} | {{source}} |

### Relations summary

- **Father:** [[{{Father_Slug}}|{{Father name}}]] ({{lifespan, place}})
- **Mother:** [[{{Mother_Slug}}|{{Mother name}}]] ({{lifespan, place}})
- **Siblings:**
  - [[{{Sibling_Slug}}|{{Sibling name}}]] ({{birth year}}{{–death year if known}})
- **Spouse{{#1 if more than one}}:** [[{{Spouse_Slug}}|{{Spouse name}}]] ({{lifespan}}) — {{m. YYYY-MM-DD, place}}; {{N children}}.
  - Parents: {{father given+surname}} & {{mother given+maiden surname}} {{(per source)}}
- **Children:**
  - [[{{Child_Slug}}|{{Child name}}]] ({{year}}{{ from union with X if multi-marriage}})

## Notes

<!-- Free-form observations, interpretations, indexer typos, alternate name
     spellings, gut-feel hypotheses. Anything the user might want to scribble
     after reading a parish scan. Not facts — facts go in the Facts table. -->

- {{Observation, hypothesis, or context not formally established.}}
- {{Indexer typos or alternate spellings noticed in Geneteka / archives.}}
- {{Sosa number and how this person sits on the user's direct line, if relevant.}}

## Research Questions

<!-- Concrete next steps. Each item should be actionable — name the act,
     year, parish, archive, or external system to check. Avoid vague
     "find more about X" wording. -->

- [ ] Locate the **{{record type}}** for {{year}} in {{parish / archive}} ({{specific catalog or signature if known}}).
- [ ] Resolve {{name / date / place discrepancy}} between {{source A}} and {{source B}}.
- [ ] Find {{external record: ship manifest, census, headstone, USC entry}} for {{event}}.
- [ ] Verify {{transcription detail}} against the original parish act.
