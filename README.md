# Welcome to Montreal

Static bilingual visitor guide, deployed from main through the existing Netlify project.

## Editorial and advertising

Three researched planning articles are published in English and French under guides/. Public credit: Welcome Montreal editorial team. Update both translations, source dates and sitemap when revising a guide. Do not claim personal visits without evidence.

Advertising scripts are disabled on all pages during the AdSense remediation. The publisher verification meta tag and ads.txt remain. Do not restore site-wide automatic ads: the directory's search, map, empty states and utility pages are not eligible editorial article placements. Review content and current consent requirements before enabling advertising on substantive articles.

## Event maintenance

The displayed timestamp describes the actual snapshot, not a guaranteed schedule. After 48 hours the directory shows a stale notice. The September 28 snapshot was cleaned on October 2 without changing its refresh date. Common add-ons and duplicate dated venue listings are filtered. Separate advertised times and dates are preserved.

Run `python update-events.py --output-only` to refresh without committing. Ticketmaster requires TM_API_KEY or the existing Hatch credential provider. All three sources must succeed; a failed source preserves the previous file and timestamp. Writes are atomic. The original Hatch push workflow is retained when --output-only is omitted; scheduling and credentials in that external environment still need verification before daily-refresh claims can be restored.
