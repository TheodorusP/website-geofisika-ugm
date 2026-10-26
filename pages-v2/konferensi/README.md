# Konferensi dan Presentasi Ilmiah

Dedicated page, no homepage widget. Suggested title **Konferensi dan Presentasi Ilmiah**, slug **konferensi**. Scope: teaching/support staff, five calendar years, with unverified staff identities left pending. No journal-ranking restriction applies.

## WordPress

Paste `01-conferences-wordpress.html` into the page Custom HTML, including its embedded filter initializer. Apply `konferensi.css` as this page's complete Custom CSS. The local `preview.html` uses that stylesheet. No site-wide CSS changes are needed.

Cards follow this order:

1. Conference date/range, conference name, confirmed city and country (or country alone), then publication/presentation/online pills.
2. Publication date and collection only when a publication is recorded. This date is never substituted as the conference date.
3. Contribution title, then all authors with verified staff highlighted.
4. Compact DOI/article button if a destination is available. No button is rendered without a link.

Pill classes: `.gf-conf-prosiding`, `.gf-conf-abstrak`, `.gf-conf-oral`, `.gf-conf-poster`, `.gf-conf-online`, all sharing `.gf-conf-pill`. Unknown presentation type produces no Oral/Poster pill. Online indicates documented online delivery of this contribution; a hybrid conference does not establish remote delivery. Author credit does not identify the presenter.

Filters: publication type, presentation type, staff, year, conference and confirmed online delivery. They combine with AND. Reset restores all results. Without JavaScript the complete list remains readable. Unavailable event dates/names are omitted. When both are unavailable, pills follow the publication information line instead. Known location information is retained separately when necessary. Date ranges omit repeated month/year components where possible; cross-year ranges retain both full dates. The year filter uses event year when known, otherwise publication year; this fallback is only for filtering/sorting and never displayed as an event date.

## Sources and matching

OpenAlex discovers candidate conference papers/abstracts, legacy proceedings articles, and recognized proceedings-series records. Crossref enriches event/collection metadata. Candidate types still require metadata/evidence checks. ISSN/journal ranks are irrelevant. Different titles are not merged by resemblance. Exact DOI or a reviewed shared `contribution_id` establishes a contribution group; within that group Prosiding takes priority over Abstrak. The current group shows its preferred publication link.

`verified-contributions.json` supplements publisher metadata with organizer-confirmed fields. The initial three EGU abstract records have official event dates and Vienna/Austria locations. EGU24-7943 is confirmed Oral/on-site by the official session program; EGU22-2087 is explicitly a virtual presentation, with its Oral/Poster classification left unknown. No presenter identity is inferred from author order.

For an indexed record, add `doi`, `verified: true`, `evidence_url`, and the verified fields among `conference_name`, `conference_start`, `conference_end`, `city`, `country`, `presentation_type` (`Oral`/`Poster`), `online` (boolean), `publication_kind` (`Prosiding`/`Abstrak`), `url`, `contribution_id`. The evidence URL must actually support the edited fields; the flag is an editorial assertion, not automatic verification merely because a URL exists.

For a standalone unindexed presentation, supply `id`, `verified: true`, `evidence_url`, `title`, `authors` (full-name list), `staff` (roster names), `conference_name` and `conference_start`; optionally the other fields above, `publication_date`, `collection`, and `staff_author_names` for exact bold highlighting. Leave `publication_kind` and `publication_date` null for an unpublished presentation. `url` is optional and may be null even when the record has an internal evidence URL.

Event locations from Crossref are split only when an explicit `City, Country` pattern has a recognized country. Country-only locations are supported. Ambiguous locations and incomplete event metadata need review. Unknown cities/countries are omitted; no affiliation or conference acronym is used to invent a location. `review.json` includes excluded candidates and incomplete metadata notes for retained records.

## Collection and GitHub

Run `python scripts/update_conference_feed.py` to collect online. The existing `OPENALEX_API_KEY` secret is reused. For initial enrichment of already captured complete journal work snapshots use `--from-journal-snapshots --as-of YYYY-MM-DD`. Offline rendering: `--offline --as-of YYYY-MM-DD`, matching the saved conference snapshot date exactly. `conference-snapshot.json` is local evidence and not included in the upload package.

Upload the extracted contents of `automation/conference-feed/conference-page-update.zip` to the existing publication repository root. It relies on the expanded journal collector's shared helpers (the October 26 publication expansion package must already be installed). It does not require the books page. Ensure `.github/workflows/update-conferences.yml` is present, then run **Actions > Update conferences > Run workflow**. The schedule is Monday 08:13 WIB; GitHub may delay scheduled runs.

After a successful run confirm `https://raw.githubusercontent.com/TheodorusP/website-geofisika-ugm/main/public/conferences-display.json`. Append the separate `automation/conference-feed/remote-loader.js` to the existing site-wide JavaScript without script tags. Keep the journal/book loaders if installed. Invalid or unavailable remote data leaves the pasted fallback page in place. Failed collection does not commit partial data. This page does not add a navigation entry automatically.

Tests: `python -m unittest discover -s scripts -p test_conference_feed.py`.
