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

Every successful run queries all configured staff, deduplicates publications and regenerates both displays. It retains three calendar years, not a rolling 36 months. Homepage: latest three. Page: all eligible results with filters, full authors and available citation metadata. New journals remain excluded until their rankings are verified in `journal-rankings.json`. When the three-year window advances, ranking evidence outside it expires; update verified rankings to maintain coverage. The schedule updates publications, not ranking evidence automatically.

Collection, tests or publishing failures prevent committing the new payload; visitors continue to see the previous successful data. A valid empty result is published as empty. Review Actions failures and `review.json` if results unexpectedly disappear.

Maintain source files in this repository once installed. This package is a copy of the local project and changes do not synchronize back automatically. No GitHub Pages configuration is required; the loader uses raw GitHub JSON.
