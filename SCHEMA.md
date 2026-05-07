# Heredis Database Schema

Reference notes on the SQLite schema used by Heredis genealogy software (`.heredis` files). Derived from `Szumiec.heredis` — Heredis macOS 18.4.0 / 25.1, `DatabaseVersion = 2504`, file format `Preferences.DatabaseVersion = 603`.

The file is a plain SQLite 3 database. It can be opened read-only with stock SQLite tooling. No proprietary encoding.

## Conventions

Heredis is French software, so most identifiers are in French. A few naming conventions repeat across every table:

| Suffix / Prefix | Meaning |
| --- | --- |
| `CodeID` | Surrogate primary key (`integer PRIMARY KEY`, i.e. ROWID alias). Every "real" entity table uses this. |
| `Xref<Entity>` | Foreign key to `<Entity>(CodeID)`. Almost always with `ON DELETE SET NULL` or `ON DELETE CASCADE`. |
| `*UCD` | Upper-Case / Diacritic-folded copy of a text column. Used for case- and accent-insensitive search and sort (e.g. `NomUCD`, `VilleUCD`, `TitreUCD`). Treat as derived. |
| `*Tri` | Sortable representation, pre-computed by triggers. `DateTri`, `MainEventNaissanceTri`, etc. are `double` Julian-day-style numbers; `100000000000.0` is the sentinel for "no date". |
| `Date*` (`DateCreation`, `DateModification`, `DateUtilisation`) | Audit timestamps maintained by triggers. Never overwrite manually. |
| `Private` | `boolean` privacy flag — many entity tables carry it. |
| `Note*RTF` | RTF-formatted variant of a text field. |

Sentinel values worth remembering:

- `Latitude = 2000000.0` / `Longitude = 2000000.0` → "no coordinates set".
- `MainEventNaissanceTri = 100000000000.0` / `MainEventDecesTri = 100000000000.0` → "no birth/death date".
- `Sexe`: `109` = male (`'m'`), `102` = female (`'f'`), `63` = unknown (`'?'`). These are ASCII codepoints.

The schema relies heavily on **triggers** to keep denormalised counts (`NombreEnfants`, `NombreUnions`, `NombreMedias`, `NombreSources`, `NombreTemoins`), the `*Tri` sort keys, and `XrefMainEvent*` "primary event" pointers in sync. Any external writer **must** either run inside the SQLite engine (so triggers fire) or replicate the trigger logic — otherwise the database will silently desynchronise. For an MCP server the safest design is **read-only** access; mutations should go through Heredis itself or a very deliberate write API.

## Entity overview

```
Individus ──┬── XrefPere/XrefMere ──> Individus
            ├── XrefUnionParents ──> Unions
            ├── XrefNom ──> Noms
            └── XrefMainEvent{Naissance,Deces} ──> Evenements

Unions ─────┬── XrefEpoux/XrefEpouse ──> Individus
            └── XrefMainEventMariage ──> Evenements

Evenements ─┬── XrefIndividuProprio XOR XrefUnionProprio   (CHECK enforces exactly one)
            ├── XrefLieu ──> Lieux
            ├── XrefSubdivision ──> Subdivisions
            └── XrefInfosRecherche ──> RechercheEvenement

Lieux ────── XrefRattachementLieu ──> Lieux                (place hierarchy)
Noms ─────── XrefRattachementNom ──> Noms                  (surname variants)
Prenoms ──── XrefRattachementPrenom ──> Prenoms            (given-name variants)
Professions  XrefRattachementProfession ──> Professions

Sources ──── XrefRepository ──> Repositories
Medias       (file-on-disk references; thumbnails in MediasVignette)
Notes        (referenced via Xref<Owner>.XrefNote — owning entity deletes the note)
```

Most relationships go through dedicated link tables (`Liens*`) rather than direct foreign keys. Because of denormalisation, almost every entity carries a `XrefNote` pointer to a single owned note, plus optional links to richer notes via the `Liens*` tables.

## Core entity tables

### `Individus` — people (2 545 rows)

Central table. One row per person.

Key columns:

- `CodeID` — PK.
- `XrefUnionParents` → `Unions` — the parents' union this person was born into. Nullable.
- `XrefPere`, `XrefMere` → `Individus` — direct parent pointers. Both nullable. `PereIntrouvable`/`MereIntrouvable` flag "known but unfindable".
- `XrefNom` → `Noms` — surname (mandatory; `ON DELETE RESTRICT`).
- `Prenoms`, `PrenomsUCD` — given names as a flat string (also linked structurally via `LiensPrenoms`).
- `Sexe` — ASCII char as int (109/102/63).
- `Numero`, `Filiation`, `Signature` — Heredis bookkeeping.
- `Confidentiel`, `Secondaire`, `SansAlliance`, `SansPosterite`, `Marque`, `FicheComplete`, `FicheCoherente` — flags.
- `Prefixe`, `Suffixe`, `Surnom`, `Titre` (each with a `*UCD` twin) — name parts.
- Derived/precomputed: `NomTri`, `MainEventNaissanceTri`, `MainEventDecesTri`, `AgeAuDecesTri`, `XrefMainEventNaissance`, `XrefMainEventDeces`, `NombreUnions`, `NombreEnfants`, `NombreMedias`, `NombreSources`. **Do not write these directly** — many triggers maintain them on insert/update of `Evenements`, `Unions`, and `Individus`.
- `XrefNote`, `XrefNoteRecherche` — owned notes (research notes are separate).

Indexes cover sort by name+birth/death and parent lookups.

### `Unions` — couples (793 rows)

One row per couple/union. `UNIQUE(XrefEpoux, XrefEpouse)` — two people can have at most one union together.

- `XrefEpoux`, `XrefEpouse` → `Individus`. Nullable (a "ghost" parent in a one-parent union is allowed).
- `TypeUnion` (int) + `TypeUnionUCD` (text). Observed values: `0` = MARRIAGE (default), `2` = SEPARATION, `3` = DIVORCE, `5` = COHABITEE. The UCD column carries the GEDCOM-style label.
- `TypeSurcharge` — free-text override for the union type.
- Derived: `MainEventMariageTri`, `XrefMainEventMariage`, `AgeUnionEpouxTri`, `AgeUnionEpouseTri`, `NombreEnfants`, `NombreMedias`.
- `XrefNote` — owned note.

Triggers maintain `Individus.NombreUnions`, the `IndividusUnions` mapping, and main-event pointers.

### `Evenements` — events (5 385 rows)

Every life event (birth, baptism, death, marriage, occupation change, residence, custom events…).

- `EventType` (int) — controlled vocabulary. Common types observed in this DB:
  | Code | Meaning (typical) |
  | --- | --- |
  | 1 | Generic / undefined |
  | 4 | **Birth** (Naissance) |
  | 6 | **Death** (Décès, alt) |
  | 8 | Baptism / christening (also counted as birth-class) |
  | 12 | **Death** / Burial (counted as death-class) |
  | 13, 15, 16, 17, 18, 21, 23, 26, 27 | Various life events (residence, occupation, etc.) |
  | 30 | Frequent — likely Residence or Occupation |
  | 54, 57 | GEDCOM custom events (`_GCID` etc.) |
  | 59, 61, 68, 69 | **Marriage-class** events (used for `XrefMainEventMariage` selection) |
  | 90, 97, 99 | Other custom |

  Birth-class = `(4, 8)`, Death-class = `(12, 6)`, Marriage-class = `(59, 61, 68, 69)`. These literal sets are baked into the triggers — keep them aligned with any code that picks "main events".

- `XrefIndividuProprio` XOR `XrefUnionProprio` — owner (CHECK constraint enforces exactly one is set). Personal events vs union events.
- `Shared` — boolean; if true, the event is a shared event (e.g. a wedding witnessed by multiple people) and other participants are linked via `LienIndividuEvenement`.
- `XrefLieu` → `Lieux`, `XrefSubdivision` → `Subdivisions` — location.
- `DateGed`, `TimeGed` — original GEDCOM-format date/time strings. `DateTri` is the numeric sort key derived from `DateGed`. `JourDeLAnnee` = day-of-year (for anniversary queries).
- `Titre`, `Cause`, `AgeSurActe`, `AgeLui`, `AgeElle`, `RechercheActe`.
- `XrefNote`, `XrefInfosRecherche` (→ `RechercheEvenement` — a research-task companion record).
- Counts: `NombreMedias`, `NombreTemoins`, `NombreSources`.

Indexes on `DateTri`, `EventType+TitreUCD`, owner Xrefs, `Shared`, `XrefLieu`, `XrefSubdivision`.

### `Lieux` — places (959 rows)

Hierarchical place dictionary. `XrefRattachementLieu` lets places be grouped (e.g. variants → canonical).

- `CodeLieu`, `Ville`, `Departement`, `Region`, `Pays` (+ UCD twins).
- `Latitude`, `Longitude` (sentinel `2000000.0` for "unset").
- `DateUtilisation` — bumped by triggers when an event references the place.
- `XrefNote`.

### `Subdivisions` — sub-places (315 rows)

Finer-grained location *within* a `Lieux` (a hamlet, a parish, an address-less landmark). Owns its own coordinates and `XrefLieu` parent.

### `Noms` — surnames (711 rows)

- `Nom`, `NomTri`, `NomUCD`.
- `XrefRattachementNom` → canonical surname.
- `UppercaseByUser` — user explicitly typed it uppercase (preserve casing on display).
- `XrefNote`.

### `Prenoms` — given names (718 rows)

- `Prenom`, `PrenomUCD`.
- `SexeDefaut` — typical sex for the name (used for inference).
- `XrefRattachementPrenom`, `UppercaseByUser`, `XrefNote`.

Linked to people via `LiensPrenoms` (per-person, with `Usuel` = "everyday name" flag) and to alternate names via `LiensAlternateNamesPrenoms`.

### `AlternateNames` — `aka` / married names / nicknames (249 rows)

One row per alternate name attached to an individual. Composes a full name (`Nom`, `Prenoms`, `Prefixe`, `Suffixe`, `Surnom`) plus a `Type`/`TypeString` describing why (e.g. married name, nickname, religious name).

### `Professions` — occupations (18 rows)

Small dictionary table. Linked to people via `LiensProfessionsIndi`. `XrefRattachementProfession` for canonicalisation.

### `Sources` — sources / citations (802 rows)

- `TypeSource`, `NatureActe`, `Certitude` — classification ints.
- `Titre`, `Document`, `Cote`, `Archivage`, `Numero`, `Auteur`, `Email`, `Url` (+ UCD twins for searchable fields).
- `DateGED`, `DateTri`.
- `XrefRepository` → `Repositories` (where this source is held).
- `XrefNote`, `XrefNoteTranscription` (separate notes for commentary vs. transcription).

### `Repositories` — archives / libraries (13 rows)

Holding institutions for sources. `Titre`, `Adresse`, `Telephone`, `Email`, `Url`, `XrefNote`.

### `Notes` — free text (3 175 rows)

- `Note` (plain text), `NoteRTF` (RTF version), `Private`.
- Notes are *owned* by exactly one entity via that entity's `XrefNote` (or a typed pointer like `XrefNoteTranscription`, `XrefNoteRecherche`). Deleting the owner deletes the note via triggers.
- Indexed for full-text via `NotesFullText` (FTS4).

### `Medias` — file references (515 rows)

Pointers to media files on disk (photos, scans). The DB stores the path, filename, file size, mtime, an xxHash32 (`Hash`), and an `Uploadable` status code:

| `Uploadable` | Meaning |
| --- | --- |
| 0 | Not yet checked |
| 100 | OK to upload |
| 200 | File missing |
| 201 | Too large |
| 202 | Format excluded |
| 203 | Hash computation failure |

Companion tables:

- `MediasVignette(XrefMedia, Vignette BLOB)` — one thumbnail per media (340 rows).
- `MediasCadres` — sub-rectangles ("frames") cropped from another media; can be tagged with an individual (e.g. tagging a face in a group photo).

### `Adresses`, `Etiquettes`, `Taches`

- `Adresses` (0 rows) — postal address records linked to people via `LiensAdresses`.
- `Etiquettes` (2 rows) — coloured tags (`Couleur` = RGBA int) attachable to individuals/events/media via `LiensEtiquette*`.
- `Taches` (0 rows) — research tasks with deadline/alert/priority. Linked to people or addresses.

## Link / junction tables

Almost all are pure many-to-many bridges with `UNIQUE` constraints to prevent duplicates. The naming pattern is `Liens<A><B>` or `Liens<A>` if singular usage.

| Table | Connects | Rows | Notes |
| --- | --- | ---: | --- |
| `IndividusUnions` | `Individus` × `Unions` | 1 536 | Maintained automatically by triggers on `Unions`. |
| `LienIndividuEvenement` | extra participants in shared events | 43 | Carries `TypeLienIndividu`, `Commentaire`, `Age`, `Titre` (e.g. witness role). |
| `LienIndividuIndividu` | person ↔ person | 0 | Generic typed relationships (godparent, adoptive, etc.). |
| `LiensPrenoms` | `Individus` × `Prenoms` | 2 960 | `Usuel` flag for everyday given name. |
| `LiensProfessionsIndi` | `Individus` × `Professions` | 46 | |
| `LiensAdresses` | `Individus` × `Adresses` | 0 | |
| `LiensAlternateNamesPrenoms` | `AlternateNames` × `Prenoms` | 226 | |
| `LiensSourceIndividu` | `Sources` × `Individus` | 3 848 | Carries `Citation`, `Quality_Source/Info/Evidence`, plus owned note + transcription. |
| `LiensSourceEvenement` | `Sources` × `Evenements` | 7 870 | Same shape as above. |
| `LiensSourcesExternes` | `Sources` ↔ external IDs | 345 | `XternalRef`, `XternalVersion`, `DateConsultation`. |
| `LiensIndividusExternes` | `Individus` ↔ external IDs | 319 | Same shape — used for FamilySearch / Geneanet / etc. cross-refs. |
| `LiensEtiquetteIndividu` / `Evenement` / `Media` | tag links | 0 each | |
| `LiensTachesIndis` / `LiensTachesAdresses` | task targets | 0 each | |
| `LiensMediaIndividu` | `Medias` × `Individus` | 201 | Has `Ordre` and `MediaPrincipal` (primary photo). |
| `LiensMediaEvenement` | `Medias` × `Evenements` | 40 | Same. |
| `LiensMediaUnion` / `LiensMediaLieu` / `LiensMediaNom` / `LiensMediaPrenom` / `LiensMediaProfession` | `Medias` × X | 0–299 | Same shape. |
| `LiensMediaSource` | `Medias` × `Sources` | 299 | |
| `LiensMediaLiensSourceIndividu` | `Medias` × `LiensSourceIndividu` | 4 | Media attached to a *specific* citation, not the source itself. |
| `LiensMediaLiensSourceEvenement` | `Medias` × `LiensSourceEvenement` | 32 | Same. |

## Auxiliary tables

- `NumerosSosa` (167 rows) — Sosa-Stradonitz numbering. `XrefIndividu` PK, `XrefDeCujus` = the root (proband), `Generation`, `SosaNumStr`, `Multiple` (implex flag). `Informations.Num1Sosa` records who Sosa #1 is.
- `OrdreEnfants(XrefIndividu, Ordre)` (77 rows) — explicit child ordering within a sibling group.
- `OrdreUnions(XrefUnion, Ordre)` (9 rows) — explicit ordering of a person's multiple unions.
- `OrdreRubriquesPerso(Ordre, TypeRubrique)` (14 rows) — UI ordering of custom field types.
- `Favoris(XrefIndividu, Titre, Ordre)` (0 rows) — user-pinned favourites; `XrefIndividu` may be NULL for separator rows.
- `BranchesMemorisees` (0 rows) — saved branch selections (ascendance/descendance).
- `DoublonsExclus(XrefIndividu1, XrefIndividu2)` (0 rows) — pairs marked "not duplicates" by the user (suppresses dedup suggestions).
- `Redactions` (0 rows) — long-form narrative text per event (`XrefEvenement`, `Type`).
- `LogsRechercheEnLigne` (46 rows) — log of online-search lookups per individual (Title + URL).
- `RechercheEvenement` (21 rows) — research-task companion records linked from `Evenements.XrefInfosRecherche`.
- `find_replace(CodeID)` (2 539 rows) — scratch table used by Heredis's find/replace tooling. Treat as transient.

## Metadata tables

- `Informations(Key text PK, Value text)` (14 rows) — key/value bag. Notable keys observed:
  - `VersionText` — Heredis version that created the file.
  - `LastModifier` — last Heredis version that wrote.
  - `DateCreation`, `DateModification` — file timestamps.
  - `DatabaseVersion` (mirrored to `Preferences.DatabaseVersion`).
  - `GUID` (mirrored to `Preferences.GUID`) — the file's UUID.
  - `Num1Sosa` — the de cujus individual ID.
  - `LocalisationEvent` — UI locale (e.g. `en`).
  - `Particules` — comma-separated list of name particles (`de`, `del`, `da`, …) for sort-key computation.
  - `IDFichier`, `UserName`, `UserComment`, `UserField`, `Signature`.
- `Preferences(DatabaseVersion, GUID)` — single-row mirror, kept in sync via triggers on `Informations`.
- `DatabaseUpgradeLog` (35 rows) — history of schema migrations Heredis has applied to this file (`VersionFrom`, `VersionTo`, `DateStart`, `DateFinish`, `Status`, `Log`).

## Full-text search

Two FTS4 virtual tables plus their shadow tables:

- `IndividusFullText` — indexes searchable fields of `Individus` (used by Heredis's quick-search box). Shadow tables: `IndividusFullText_content`, `IndividusFullText_segdir`, `IndividusFullText_segments`, `IndividusFullText_docsize`, `IndividusFullText_stat`.
- `NotesFullText` — indexes `Notes.Note`. Same shadow tables. The `xrefNote` column links FTS rows back to `Notes.CodeID`. A trigger on `Notes` deletes FTS rows on note delete.

For an MCP server, querying FTS directly with `MATCH` is far cheaper than `LIKE '%…%'` over the base tables.

## Triggers — what to know

You don't normally need to read the trigger bodies, but you should know what they enforce, because they explain otherwise-baffling state changes:

1. **Counts** (`NombreEnfants`, `NombreUnions`, `NombreMedias`, `NombreSources`, `NombreTemoins`) are recomputed on every relevant insert/update/delete.
2. **Sort keys** (`*Tri`, `MainEventNaissanceTri`, `MainEventDecesTri`, `MainEventMariageTri`, `AgeAuDecesTri`, `AgeUnion*Tri`) are recomputed when the underlying event changes.
3. **`XrefMainEvent*`** pointers are auto-selected when events of the right `EventType` are inserted/updated/deleted, ordered by `(DateTri = 0.0)` then `EventType` then `DateTri`. Birth picks earliest type-4-or-8; death picks the latest of types 12/6 (DESC); marriage prefers types 61 → 68 → 69 → 59.
4. **Cascade-deleting owned notes**: deleting an `Individus` / `Evenements` / `Unions` / `Lieux` / `Noms` / `Prenoms` / `Sources` / `Repositories` / `Adresses` / `Medias` / `RechercheEvenement` / `LiensSource*` row deletes the `Notes` row referenced by its `XrefNote(Transcription/Recherche)`.
5. **`DateModification` propagation**: editing a child entity bumps the parent's `DateModification` (e.g. editing an event bumps the owner individual; editing a person bumps their unions). Useful for sync.
6. **`IndividusUnions`** is mirror-maintained from `Unions.XrefEpoux`/`XrefEpouse` — never write to it directly.
7. **`Informations` ↔ `Preferences`** are kept in lockstep for `DatabaseVersion` and `GUID`.
8. **Parent flags**: setting `XrefPere`/`XrefMere` clears `PereIntrouvable`/`MereIntrouvable` on the child and `SansPosterite` on the parent. Clearing both parents also clears `XrefUnionParents`.

## Implications for the MCP server

- **Read-only is the safe default.** All `*Tri`, `Nombre*`, `XrefMainEvent*`, and the `IndividusUnions` mirror are trigger-maintained; bypassing the triggers (or even running ATTACH-style operations against the file while Heredis is open) will desynchronise it.
- **Use UCD columns for matching.** User input should be folded the same way Heredis folds (uppercase, accents stripped) before comparing. Names, places, occupations, source titles all duplicate themselves into `*UCD` for this reason.
- **Prefer FTS for free-text search** over `LIKE`.
- **Identifiers are local.** `CodeID` is a per-file ROWID, not a stable cross-file identifier. For cross-file references use `Informations.GUID` plus the local `CodeID`, or the `LiensIndividusExternes` / `LiensSourcesExternes` table contents.
- **Open the file with `PRAGMA query_only = 1`** to be safe; ideally also `mode=ro` in the URI.
- **Watch for shared events.** `Evenements.Shared = 1` means additional participants exist in `LienIndividuEvenement` — joining only on `XrefIndividuProprio` will under-report.
- **Sex is an ASCII codepoint**, not 0/1/2. Translate at the boundary.
- **Date sort keys are doubles, not real dates.** `DateGed`/`TimeGed` hold the original GEDCOM strings (which can be approximate, ranged, or "before/after"). Reconstruct user-visible dates from `DateGed`, but sort and filter using `DateTri`.
