# Weekly Geofisika publications

Prepared for https://github.com/TheodorusP/website-geofisika-ugm with default branch `main`.
This is a publication-only package. It contains no website backups, credentials or raw research snapshots.

## Upload

1. Extract `github-upload.zip` locally. Upload the CONTENTS of `github-upload` into the repository root, preserving paths. Do not upload the ZIP itself or an enclosing `github-upload` directory.
2. Ensure `.github/workflows/update-publications.yml` exists on GitHub. Windows/browser uploads may omit the hidden `.github` folder: use GitHub **Add file > Create new file**, enter that full path, and paste the YAML from the extracted file if needed.
3. The initial `public/publications-display.json` contains the existing 22 October 2026 snapshot. It does not claim a new collection.
4. Optionally add your OpenAlex API key as repository **Settings > Secrets and variables > Actions > New repository secret**, name `OPENALEX_API_KEY`. Do not paste a key into code, WordPress or chat. If unauthenticated collection fails, configure this secret and rerun.
5. Open **Actions > Update publications > Run workflow** on `main`. Wait for a green result. If Actions is disabled, enable it in repository settings. Branch protection or organization policy may need adjustment to permit the workflow to commit its generated data.
6. Confirm the JSON opens at https://raw.githubusercontent.com/TheodorusP/website-geofisika-ugm/main/public/publications-display.json and its `as_of` date matches the successful collection.

## Connect WordPress once

1. Replace the dedicated publication page Custom HTML with the included `pages-v2/publikasi-jurnal/01-publications-wordpress.html`. Its filter initializer can now reconnect after a remote refresh. Keep the existing page-local CSS.
2. Keep the current homepage publication HTML and site-wide CSS.
3. Append the contents of `automation/publication-feed/remote-loader.js` to the existing site-wide JavaScript, without script tags. This is a standalone addition; do not replace the header/navigation JavaScript with it.
4. Clear any website cache, open both pages, and check the publication date and page filters. If downloads are blocked, the original pasted HTML remains visible. Browser developer tools show the download or validation error.

If the default branch is not `main`, update the endpoint in `remote-loader.js` before installing it.
The loader only downloads public generated HTML inside JSON; it does not fetch OpenAlex or expose an API key in the browser. A restrictive Content Security Policy or network filter on the UGM site may block the raw GitHub endpoint; this must be checked on the published site.

## Operation

The workflow is scheduled for Monday 00:23 UTC (07:23 WIB). GitHub schedules may be delayed; public repositories' scheduled workflows can be disabled after 60 days without repository activity. Successful weekly data commits normally provide activity; check Actions periodically and re-enable the schedule if needed. Manual runs remain available.

Every successful run queries all configured staff, checks ranking sources, deduplicates publications and regenerates both displays. It retains five calendar years, not a rolling 60 months. Homepage: latest three. Page: all eligible results with filters, full authors and available citation metadata. New journals remain excluded until their rankings are verified in `journal-rankings.json`. When the five-year window advances, ranking evidence outside it expires.

## Automatic ranking checks

Upload the contents of `ranking-automation-update.zip` to the existing repository root to add this feature. This smaller upgrade does not overwrite your collected publication data or ranking registry. Ensure the hidden `.github/workflows/update-publications.yml` file is updated too, then manually run **Update publications**.

The collector now checks the official SCImago annual exports for the completed years in the five-year window. It imports only explicit best-quartile fields matched by ISSN for journals encountered in staff works. Q3/Q4 are now eligible too; the latest verified rank replaces older evidence. Full exported datasets are not redistributed; only matching evidence records, source URLs and hashes are saved.

Sinta checks currently support one configured primary publisher source: Riset Geologi dan Pertambangan's BRIN accreditation notice. That adapter requires a matching ISSN, explicit rank, decree and validity range. It verifies only calendar years strictly inside issue-based boundaries. Other Sinta journals, image/PDF-only certificates, boundary years and ambiguous renewals remain subject to review; this is not a general Sinta database crawler. Add narrowly tested publisher adapters to `ranking-sources.json` to expand coverage. Current Sinta badges alone are not treated as historical accreditation evidence.

Requests respect robots.txt and stop on HTTP failures, CAPTCHA/HTML exports, certificate errors, unrecognized fields or ambiguous evidence. There is no bypass of access blocks. Automatic access and reuse conditions for unrestricted SCImago/Sinta bulk harvesting have not been established; this implementation attempts ordinary official exports and the configured publisher notice, not unrestricted crawling. Their availability on the GitHub runner must be checked in the first run.

`widgets/publication-feed/ranking-review.json` records each source's status and journals without evidence in the current window, as well as conflicting ranks. Existing evidence is retained when a source is unavailable. Same-year conflicting manual and automatic records are preserved for review; the publication selector excludes the conflicting system/year. A green workflow with a ranking warning means publication collection completed, but some ranking sources were not verified. Check the report before treating the ranking refresh as successful.

Offline regeneration never performs ranking checks or updates their verification dates. The local initial test on 22 October 2026 encountered certificate errors for every live source and imported no new rankings. Parser tests validate source formats and safeguards, but do not prove live source availability. Some review candidates may be journals from works later excluded for staff identity or article type; the publication eligibility checks still run independently.

Collection, tests or publishing failures prevent committing the new payload; visitors continue to see the previous successful data. A valid empty result is published as empty. Review Actions failures and `review.json` if results unexpectedly disappear.

Maintain source files in this repository once installed. This package is a copy of the local project and changes do not synchronize back automatically. No GitHub Pages configuration is required; the loader uses raw GitHub JSON.

## Expanded journal roster and five-year window

Upload the contents of `publication-expansion-update.zip` to the existing repository root, preserving paths and replacing the supplied source files. It includes updated teaching-staff aliases, a separate six-person support roster, the five-year collector/ranking window, tests and page CSS. It does not overwrite the live publications JSON or existing ranking registry. Run Update publications afterward. The remote widget/page will read the new data automatically; update WordPress page-local publikasi-jurnal.css for Q3/Q4 colors. No site-wide JavaScript replacement is necessary. Optionally update the pasted fallback HTML from your successful GitHub run.

Window: 2022-2026 for the 2026 run. Allowed ranks: Q1-Q4, Sinta 1/2. Unknown rankings are still excluded. Older papers need evidence no later than their publication year. Teaching staff: 17. Support staff: 6; Budiarjo and Pamungkas Yuliantoro have verified identities, while Catur Jaka Priyana, Supriyanta, Yan Hendra Kurniawan and Nindy Husnul Majid remain pending. Pending identities do not stop collection and are reported explicitly in coverage.json. No namesake profile is assigned based on name alone.
