"""SQL query layer. All functions take an open read-only sqlite3.Connection."""

from __future__ import annotations

import sqlite3

from polish_genealogy_mcp.sources.heredis.constants import (
    BIRTH_EVENT_TYPES,
    DEATH_EVENT_TYPES,
    EVENT_TYPE_LABELS,
    UNION_TYPE_LABELS,
)
from polish_genealogy_mcp.sources.heredis.db import (
    coord_or_none,
    datetri_or_none,
    fold_ucd,
    sex_label,
    year_bounds,
)
from polish_genealogy_mcp.sources.heredis.models import (
    EventDetail,
    EventSearchResult,
    EventSummary,
    FamilyView,
    PersonDetail,
    PersonSearchResult,
    PersonSummary,
    PlaceRef,
    PlaceSearchResult,
    SourceSearchResult,
    SourceSummary,
    UnionSummary,
)


def _fetch_note_text(conn: sqlite3.Connection, code_id: int | None) -> str | None:
    if code_id is None:
        return None
    row = conn.execute(
        "SELECT Note FROM Notes WHERE CodeID = ?",
        (code_id,),
    ).fetchone()
    if row is None:
        return None
    text = (row["Note"] or "").strip()
    return text or None


def _row_place(row: sqlite3.Row | None) -> PlaceRef | None:
    if row is None or row["CodeID"] is None:
        return None
    return PlaceRef(
        code_id=row["CodeID"],
        city=row["Ville"] or None,
        department=row["Departement"] or None,
        region=row["Region"] or None,
        country=row["Pays"] or None,
        latitude=coord_or_none(row["Latitude"]),
        longitude=coord_or_none(row["Longitude"]),
    )


def _fetch_place(conn: sqlite3.Connection, code_id: int | None) -> PlaceRef | None:
    if code_id is None:
        return None
    row = conn.execute(
        "SELECT CodeID, Ville, Departement, Region, Pays, Latitude, Longitude "
        "FROM Lieux WHERE CodeID = ?",
        (code_id,),
    ).fetchone()
    return _row_place(row)


def _event_summary(conn: sqlite3.Connection, row: sqlite3.Row | None) -> EventSummary | None:
    if row is None:
        return None
    place = _fetch_place(conn, row["XrefLieu"])
    et = row["EventType"]
    return EventSummary(
        code_id=row["CodeID"],
        event_type=et,
        event_type_label=EVENT_TYPE_LABELS.get(et, "Unknown"),
        date_ged=row["DateGed"] or None,
        date_tri=datetri_or_none(row["DateTri"]),
        place=place,
        title=row["Titre"] or None,
    )


def _person_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> PersonSummary:
    birth = (
        conn.execute(
            "SELECT CodeID, EventType, DateGed, DateTri, XrefLieu, Titre "
            "FROM Evenements WHERE CodeID = ?",
            (row["XrefMainEventNaissance"],),
        ).fetchone()
        if row["XrefMainEventNaissance"]
        else None
    )
    death = (
        conn.execute(
            "SELECT CodeID, EventType, DateGed, DateTri, XrefLieu, Titre "
            "FROM Evenements WHERE CodeID = ?",
            (row["XrefMainEventDeces"],),
        ).fetchone()
        if row["XrefMainEventDeces"]
        else None
    )
    return PersonSummary(
        code_id=row["CodeID"],
        surname=row["Nom"] or "",
        given_names=row["Prenoms"] or "",
        sex=sex_label(row["Sexe"]),
        birth=_event_summary(conn, birth),
        death=_event_summary(conn, death),
    )


_PERSON_SELECT_BASE = """
    SELECT i.CodeID, i.Sexe, i.Prenoms, i.PrenomsUCD, i.NomTri,
           i.XrefMainEventNaissance, i.XrefMainEventDeces,
           i.Confidentiel, i.Numero, i.Prefixe, i.Suffixe, i.Surnom, i.Titre,
           i.Profession, i.XrefPere, i.XrefMere, i.XrefUnionParents,
           i.NombreUnions, i.NombreEnfants, i.NombreSources, i.NombreMedias,
           i.XrefNote, i.XrefNoteRecherche,
           n.Nom, n.NomUCD
    FROM Individus i
    LEFT JOIN Noms n ON n.CodeID = i.XrefNom
"""


def search_persons(
    conn: sqlite3.Connection,
    *,
    name: str | None = None,
    surname: str | None = None,
    given_name: str | None = None,
    sex: str | None = None,
    born_after: int | None = None,
    born_before: int | None = None,
    died_after: int | None = None,
    died_before: int | None = None,
    place: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PersonSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    where: list[str] = []
    params: list[object] = []

    if surname:
        where.append("n.NomUCD LIKE ?")
        params.append(f"%{fold_ucd(surname)}%")
    if given_name:
        where.append("i.PrenomsUCD LIKE ?")
        params.append(f"%{fold_ucd(given_name)}%")
    if name:
        # Match either surname or given names.
        folded = fold_ucd(name)
        where.append("(n.NomUCD LIKE ? OR i.PrenomsUCD LIKE ?)")
        params.extend([f"%{folded}%", f"%{folded}%"])
    if sex:
        from polish_genealogy_mcp.sources.heredis.constants import SEX_TO_CODE

        code = SEX_TO_CODE.get(sex.upper())
        if code is not None:
            where.append("i.Sexe = ?")
            params.append(code)

    if born_after is not None or born_before is not None:
        lo, hi = year_bounds(born_after, born_before)
        where.append(
            "EXISTS (SELECT 1 FROM Evenements e WHERE e.XrefIndividuProprio = i.CodeID "
            f"AND e.EventType IN ({','.join('?' * len(BIRTH_EVENT_TYPES))}) "
            "AND e.DateTri BETWEEN ? AND ?)"
        )
        params.extend(BIRTH_EVENT_TYPES)
        params.extend([lo, hi])

    if died_after is not None or died_before is not None:
        lo, hi = year_bounds(died_after, died_before)
        where.append(
            "EXISTS (SELECT 1 FROM Evenements e WHERE e.XrefIndividuProprio = i.CodeID "
            f"AND e.EventType IN ({','.join('?' * len(DEATH_EVENT_TYPES))}) "
            "AND e.DateTri BETWEEN ? AND ?)"
        )
        params.extend(DEATH_EVENT_TYPES)
        params.extend([lo, hi])

    if place:
        where.append(
            "EXISTS (SELECT 1 FROM Evenements e JOIN Lieux l ON l.CodeID = e.XrefLieu "
            "WHERE e.XrefIndividuProprio = i.CodeID AND l.VilleUCD LIKE ?)"
        )
        params.append(f"%{fold_ucd(place)}%")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM Individus i LEFT JOIN Noms n ON n.CodeID = i.XrefNom {where_sql}",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"{_PERSON_SELECT_BASE} {where_sql} "
        "ORDER BY i.NomTri, i.PrenomsUCD, i.MainEventNaissanceTri "
        "LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    items = [_person_summary(conn, r) for r in rows]
    return PersonSearchResult(total=total, limit=limit, offset=offset, items=items)


def get_person(conn: sqlite3.Connection, code_id: int) -> PersonDetail | None:
    row = conn.execute(
        f"{_PERSON_SELECT_BASE} WHERE i.CodeID = ?",
        (code_id,),
    ).fetchone()
    if row is None:
        return None

    base = _person_summary(conn, row)

    sosa = conn.execute(
        "SELECT SosaNumStr, Generation FROM NumerosSosa WHERE XrefIndividu = ?",
        (code_id,),
    ).fetchone()

    event_rows = conn.execute(
        "SELECT CodeID, EventType, DateGed, DateTri, XrefLieu, Titre "
        "FROM Evenements WHERE XrefIndividuProprio = ? ORDER BY DateTri",
        (code_id,),
    ).fetchall()
    events = [_event_summary(conn, e) for e in event_rows]

    union_rows = conn.execute(
        "SELECT CodeID FROM Unions WHERE XrefEpoux = ? OR XrefEpouse = ? ORDER BY MainEventMariageTri",
        (code_id, code_id),
    ).fetchall()
    unions = [u for u in (_load_union(conn, r["CodeID"]) for r in union_rows) if u is not None]

    return PersonDetail(
        **base.model_dump(),
        prefix=row["Prefixe"] or None,
        suffix=row["Suffixe"] or None,
        nickname=row["Surnom"] or None,
        title=row["Titre"] or None,
        occupation=row["Profession"] or None,
        confidential=bool(row["Confidentiel"]),
        father_id=row["XrefPere"],
        mother_id=row["XrefMere"],
        union_parents_id=row["XrefUnionParents"],
        n_unions=row["NombreUnions"] or 0,
        n_children=row["NombreEnfants"] or 0,
        n_sources=row["NombreSources"] or 0,
        n_medias=row["NombreMedias"] or 0,
        sosa_number=sosa["SosaNumStr"] if sosa else None,
        sosa_generation=sosa["Generation"] if sosa else None,
        events=events,
        unions=unions,
        notes=[t for t in [_fetch_note_text(conn, row["XrefNote"])] if t],
        research_notes=[t for t in [_fetch_note_text(conn, row["XrefNoteRecherche"])] if t],
    )


def _load_union(conn: sqlite3.Connection, union_id: int) -> UnionSummary | None:
    row = conn.execute(
        "SELECT CodeID, XrefEpoux, XrefEpouse, TypeUnion, XrefMainEventMariage "
        "FROM Unions WHERE CodeID = ?",
        (union_id,),
    ).fetchone()
    if row is None:
        return None
    marriage_event = (
        conn.execute(
            "SELECT CodeID, EventType, DateGed, DateTri, XrefLieu, Titre "
            "FROM Evenements WHERE CodeID = ?",
            (row["XrefMainEventMariage"],),
        ).fetchone()
        if row["XrefMainEventMariage"]
        else None
    )
    children = conn.execute(
        "SELECT CodeID FROM Individus WHERE XrefUnionParents = ? ORDER BY MainEventNaissanceTri",
        (union_id,),
    ).fetchall()
    return UnionSummary(
        code_id=row["CodeID"],
        type=UNION_TYPE_LABELS.get(row["TypeUnion"], "Unknown"),
        husband_id=row["XrefEpoux"],
        wife_id=row["XrefEpouse"],
        marriage=_event_summary(conn, marriage_event),
        children_ids=[c["CodeID"] for c in children],
    )


def get_family(conn: sqlite3.Connection, code_id: int) -> FamilyView | None:
    person_row = conn.execute(
        f"{_PERSON_SELECT_BASE} WHERE i.CodeID = ?",
        (code_id,),
    ).fetchone()
    if person_row is None:
        return None
    person = _person_summary(conn, person_row)

    father = mother = None
    if person_row["XrefPere"]:
        r = conn.execute(
            f"{_PERSON_SELECT_BASE} WHERE i.CodeID = ?",
            (person_row["XrefPere"],),
        ).fetchone()
        father = _person_summary(conn, r) if r else None
    if person_row["XrefMere"]:
        r = conn.execute(
            f"{_PERSON_SELECT_BASE} WHERE i.CodeID = ?",
            (person_row["XrefMere"],),
        ).fetchone()
        mother = _person_summary(conn, r) if r else None

    sibling_rows: list[sqlite3.Row] = []
    if person_row["XrefPere"] or person_row["XrefMere"]:
        sibling_rows = conn.execute(
            f"{_PERSON_SELECT_BASE} WHERE i.CodeID <> ? AND ("
            "(i.XrefPere = ? AND ? IS NOT NULL) OR (i.XrefMere = ? AND ? IS NOT NULL)) "
            "ORDER BY i.MainEventNaissanceTri",
            (
                code_id,
                person_row["XrefPere"],
                person_row["XrefPere"],
                person_row["XrefMere"],
                person_row["XrefMere"],
            ),
        ).fetchall()
    siblings = [_person_summary(conn, r) for r in sibling_rows]

    union_rows = conn.execute(
        "SELECT CodeID FROM Unions WHERE XrefEpoux = ? OR XrefEpouse = ? "
        "ORDER BY MainEventMariageTri",
        (code_id, code_id),
    ).fetchall()
    unions = [u for u in (_load_union(conn, r["CodeID"]) for r in union_rows) if u is not None]

    children_by_union: dict[int, list[PersonSummary]] = {}
    for u in unions:
        rows = conn.execute(
            f"{_PERSON_SELECT_BASE} WHERE i.XrefUnionParents = ? "
            "ORDER BY i.MainEventNaissanceTri",
            (u.code_id,),
        ).fetchall()
        children_by_union[u.code_id] = [_person_summary(conn, r) for r in rows]

    return FamilyView(
        person=person,
        father=father,
        mother=mother,
        siblings=siblings,
        unions=unions,
        children_by_union=children_by_union,
    )


def search_events(
    conn: sqlite3.Connection,
    *,
    event_type: int | None = None,
    title: str | None = None,
    place: str | None = None,
    person_id: int | None = None,
    after_year: int | None = None,
    before_year: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> EventSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    where: list[str] = []
    params: list[object] = []

    if event_type is not None:
        where.append("e.EventType = ?")
        params.append(event_type)
    if title:
        where.append("e.TitreUCD LIKE ?")
        params.append(f"%{fold_ucd(title)}%")
    if person_id is not None:
        where.append(
            "(e.XrefIndividuProprio = ? OR EXISTS "
            "(SELECT 1 FROM LienIndividuEvenement le "
            "WHERE le.XrefEvenement = e.CodeID AND le.XrefIndividuOrig = ?))"
        )
        params.extend([person_id, person_id])
    if place:
        where.append(
            "EXISTS (SELECT 1 FROM Lieux l WHERE l.CodeID = e.XrefLieu " "AND l.VilleUCD LIKE ?)"
        )
        params.append(f"%{fold_ucd(place)}%")
    if after_year is not None or before_year is not None:
        lo, hi = year_bounds(after_year, before_year)
        where.append("e.DateTri BETWEEN ? AND ?")
        params.extend([lo, hi])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM Evenements e {where_sql}", params).fetchone()[0]

    rows = conn.execute(
        "SELECT e.CodeID, e.EventType, e.DateGed, e.DateTri, e.XrefLieu, e.Titre "
        f"FROM Evenements e {where_sql} ORDER BY e.DateTri LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    items = [_event_summary(conn, r) for r in rows]
    return EventSearchResult(total=total, limit=limit, offset=offset, items=items)


def get_event(conn: sqlite3.Connection, code_id: int) -> EventDetail | None:
    row = conn.execute(
        "SELECT CodeID, EventType, DateGed, DateTri, XrefLieu, Titre, "
        "Cause, AgeSurActe, Private, Shared, "
        "XrefIndividuProprio, XrefUnionProprio, XrefNote, "
        "NombreSources, NombreMedias "
        "FROM Evenements WHERE CodeID = ?",
        (code_id,),
    ).fetchone()
    if row is None:
        return None

    base = _event_summary(conn, row)

    participant_rows = conn.execute(
        "SELECT le.XrefIndividuOrig AS person_id, le.TypeLienIndividu AS link_type, "
        "le.Commentaire AS comment, le.Age AS age, le.Titre AS title "
        "FROM LienIndividuEvenement le WHERE le.XrefEvenement = ?",
        (code_id,),
    ).fetchall()
    participants = [dict(r) for r in participant_rows]

    return EventDetail(
        **base.model_dump(),
        cause=row["Cause"] or None,
        age_on_act=row["AgeSurActe"] or None,
        private=bool(row["Private"]),
        shared=bool(row["Shared"]),
        owner_person_id=row["XrefIndividuProprio"],
        owner_union_id=row["XrefUnionProprio"],
        participants=participants,
        n_sources=row["NombreSources"] or 0,
        n_medias=row["NombreMedias"] or 0,
        notes=[t for t in [_fetch_note_text(conn, row["XrefNote"])] if t],
    )


def search_places(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> PlaceSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    folded = f"%{fold_ucd(query)}%"

    where = (
        "WHERE VilleUCD LIKE ? OR DepartementUCD LIKE ? " "OR RegionUCD LIKE ? OR PaysUCD LIKE ?"
    )
    params = [folded, folded, folded, folded]
    total = conn.execute(f"SELECT COUNT(*) FROM Lieux {where}", params).fetchone()[0]
    rows = conn.execute(
        "SELECT CodeID, Ville, Departement, Region, Pays, Latitude, Longitude "
        f"FROM Lieux {where} ORDER BY VilleUCD LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = [p for p in (_row_place(r) for r in rows) if p is not None]
    return PlaceSearchResult(total=total, limit=limit, offset=offset, items=items)


def search_sources(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> SourceSearchResult:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    folded = f"%{fold_ucd(query)}%"

    where = "WHERE s.TitreUCD LIKE ? OR s.DocumentUCD LIKE ? OR s.AuteurUCD LIKE ?"
    params = [folded, folded, folded]
    total = conn.execute(f"SELECT COUNT(*) FROM Sources s {where}", params).fetchone()[0]
    rows = conn.execute(
        "SELECT s.CodeID, s.Titre, s.Document, s.Auteur, s.Url, s.DateGED, "
        "s.XrefRepository, r.Titre AS RepoTitre "
        "FROM Sources s LEFT JOIN Repositories r ON r.CodeID = s.XrefRepository "
        f"{where} ORDER BY s.TitreUCD LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = [
        SourceSummary(
            code_id=r["CodeID"],
            title=r["Titre"] or None,
            document=r["Document"] or None,
            author=r["Auteur"] or None,
            repository_id=r["XrefRepository"],
            repository_title=r["RepoTitre"] or None,
            url=r["Url"] or None,
            date_ged=r["DateGED"] or None,
        )
        for r in rows
    ]
    return SourceSearchResult(total=total, limit=limit, offset=offset, items=items)


def get_source(conn: sqlite3.Connection, code_id: int) -> SourceSummary | None:
    row = conn.execute(
        "SELECT s.CodeID, s.Titre, s.Document, s.Auteur, s.Url, s.DateGED, "
        "s.XrefRepository, r.Titre AS RepoTitre "
        "FROM Sources s LEFT JOIN Repositories r ON r.CodeID = s.XrefRepository "
        "WHERE s.CodeID = ?",
        (code_id,),
    ).fetchone()
    if row is None:
        return None
    return SourceSummary(
        code_id=row["CodeID"],
        title=row["Titre"] or None,
        document=row["Document"] or None,
        author=row["Auteur"] or None,
        repository_id=row["XrefRepository"],
        repository_title=row["RepoTitre"] or None,
        url=row["Url"] or None,
        date_ged=row["DateGED"] or None,
    )
