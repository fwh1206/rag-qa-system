# Third-party frontend libraries

The project vendors the following mature open-source browser libraries so the
web UI does not depend on third-party CDNs at runtime. Full license texts are
kept in `licenses/`.

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| marked | 18.0.9 | MIT | Render assistant answers as Markdown |
| dompurify | 3.4.13 | MPL-2.0 OR Apache-2.0 | Sanitize rendered HTML against XSS |
| highlight.js | 11.12.0 | BSD-3-Clause | Syntax-highlight code blocks in answers |
| chart.js | 4.5.1 | MIT | Draw the recent-chat trend chart |
| cytoscape.js | 3.34.1 | MIT | Render document knowledge graphs |

`highlight.min.js` is distributed via the official `@highlightjs/cdn-assets`
package, which matches the `highlight.js` release.
