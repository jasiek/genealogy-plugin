---
name: research-person
description: "Perform research on a person with the given name"
---

# Research person skill

Perform genealogy research for person named $ARGUMENTS.

## Instructions

For each person, maintain an Obsidian-style markdown file. Name of the file should be persons/<Firstname>_<Lastname>_<ID>.md
where ID is a unique identifier.

Use Obsidian's aliases to make the note cross-referenceable by listing heredis record identifier, and GEDCOM id.

This file contains a number of sections:
- Research Journal - This contains sub-sections keyed by hyperlinked date ([[2026-05-18]]) which contains
  bullet points about research done on a particular day - which sources were checked, and so on.
- Facts - contains facts established about a person. Each fact must contain a hyperlink to a source, be it
  a note, a picture file, or another URL.
- Notes - Section with additional hints edited by the user.
- Research Questions - bullet-point list of questions we're trying to answer.

- When looking for existing, established evidence, check sources of truth, such as tool:Heredis, or tool:GEDCOM.
  Heredis files or GED files should be in the current directory.
- When referring to other people, use hyperlinks. 
