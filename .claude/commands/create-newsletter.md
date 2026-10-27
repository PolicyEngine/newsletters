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
   - Generate a white `section-pad` section with key findings, an optional image and the teal button

3. **Compile newsletter** following "Newsletter Template Structure" in `CLAUDE.md`:
   - Copy the most recent edition in `editions/` to a new file named `YYYY-MM-DD-{audience}.html` with the planned send date
   - Set the `<title>` and the header date to the send date (e.g. `PolicyEngine UK &middot; 27 October 2026`)
   - Keep the header's white PNG logo, pinned to its commit SHA
   - Put the event in the hero if `--event` provided; otherwise use the hero for the edition's headline
   - Replace the old sections with the research sections
   - Write the hidden preheader `<div>`, and use the same words for `--preview` when uploading
   - Commit and push any new images, then replace each `<commit-sha>` in image URLs with the full 40-character SHA of that pushed commit (never a branch name or `main`)
   - Keep the sign-off, and the footer with all four Mailchimp merge tags
   - Run `bash scripts/lint-newsletters.sh`

4. **Show result**:
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
