# Lessons Learned

- **API access limits:** Standard public search engines (Google, DuckDuckGo) are either rate-limiting the environment or deploying captchas, making standard web-scraping highly unreliable.
- **Pivot to domain-specific platforms:** When general search is blocked, querying specific platforms (like GitHub via its API for an IT/bootcamp related topic) is extremely effective. The `inkua` organization on GitHub provided verifiable evidence of Frank's work.
- **Homonym resolution:** Searching for "Ezequiel" in the InkuA context turned up another team member, "Gonzalo Ezequiel Vega Echeverría". This confirms the necessity of strict identity anchors beyond just a first name.

**Improved prompt clause:**
"If general search engines return no results or block access, immediately pivot to domain-specific platform APIs (e.g., GitHub for IT projects) relevant to the organization. Always verify the full name to distinguish between team members with the same first name."
