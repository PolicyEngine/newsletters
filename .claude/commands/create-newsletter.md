---
description: Create a newsletter from blog posts and event information
argument-hint: --posts post1,post2 [--event event-slug] [--audience uk|us]
---

Create a new newsletter HTML file from PolicyEngine research posts and optional event information.

## Usage

```bash
/create-newsletter --posts uk-carbon-tax,uk-vat --event nov-3-london --audience uk
/create-newsletter --posts harris-ctc,trump-tax --audience us
```

## Process

1. **Parse arguments** from `$ARGUMENTS`:
   - `--posts`: Comma-separated list of blog post slugs
   - `--event`: Optional event slug (looks for matching .md file or Luma link)
   - `--audience`: Target audience (uk, us, or all) - defaults to all

2. **For each post**:
   - Use the `newsletter-writer` subagent to generate HTML section
   - Find post in `../policyengine-app/src/posts/articles/`
   - Generate section with key findings and styling

3. **Compile newsletter**:
   - Create new HTML file in `editions/` with today's date
   - Add header with logo
   - Insert event hero section if `--event` provided
   - Add research sections
   - Add footer with Mailchimp merge tags

4. **Check comparables are fresh** (required before sending, Max 2026-10-21):
   - Run `python -m newsletter_uploader.comparables editions/<new file>`. Every
     policyengine.org analysis the edition links needs a comparables search in
     PolicyEngine/policyengine-scorecard dated within the scorecard's promotion
     window (7 days by default) before the edition's date, with no gap still pending.
   - For each analysis it lists, run the comparables review with search kind
     `prepromotion` (`/comparables-review` and the `policyengine-comparables-review`
     skill in the PolicyEngine plugin), merge the scorecard PR, and check again.
     CI and `upload-newsletter` both refuse an edition that fails this.
   - If the fresh search finds a comparable whose figure differs from ours by more than
     the threshold, the edition says so beside our figure, or leaves the analysis out
     until the gap is explained.

5. **Show result**:
   - Path to generated file
   - Preview of content
   - Next steps: upload with `upload-newsletter` command

## Example Output

```
✅ Newsletter created: editions/2025-10-02-uk.html

Sections included:
  • Event: PolicyEngine 2.0 Launch
  • Research: Carbon tax and dividend analysis
  • Research: VAT threshold impact study

Next steps:
  upload-newsletter editions/2025-10-02-uk.html --audience uk --subject "..." --preview "..."
```
