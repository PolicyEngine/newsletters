---
description: Upload newsletter to Mailchimp as a draft campaign
argument-hint: <html-file> --audience <uk|us|all> --subject "..." --preview "..."
---

Upload a newsletter HTML file to Mailchimp as a draft campaign with audience targeting.

## Usage

```bash
/upload-draft editions/2025-10-02-uk.html --audience uk --subject "Subject line" --preview "Preview text"
```

## Process

This is a wrapper around the `upload-newsletter` command that:

1. Validates the HTML file exists
2. Prompts for required fields if missing
3. Runs the upload command, which first checks that every policyengine.org analysis
   the edition links has a fresh comparables search in the scorecard, judged on the
   later of the edition's date and today (`src/newsletter_uploader/comparables.py`), and
   refuses to upload otherwise, or when the file name does not start with its date. Fix
   it by running the comparables review (search kind `prepromotion`), never by renaming
   or re-dating the file. To change a draft already uploaded, run the same command with
   `--campaign-id`; it runs the same check.
4. Shows the Mailchimp edit URL

## Arguments

- `html-file`: Path to newsletter HTML file (required)
- `--audience`: Target audience - `uk`, `us`, or `all` (required)
  - `uk`: Only UK subscribers (COUNTRY = "United Kingdom")
  - `us`: All non-UK subscribers (COUNTRY ≠ "United Kingdom")
  - `all`: All subscribers
- `--subject`: Email subject line (required)
- `--preview`: Preview text shown in inbox (required)
- `--title`: Optional internal campaign title (defaults to filename)

## Implementation

```bash
upload-newsletter $ARGUMENTS
```

## Example

```bash
/upload-draft editions/2025-10-02-uk.html \
  --audience uk \
  --subject "Join us for PolicyEngine 2.0 launch • 3 November in London" \
  --preview "Register for our flagship event at Central Hall Westminster. Plus: happy hour tonight, and new research on carbon taxes and VAT."
```

Output:
```
📧 Creating Mailchimp draft campaign
   File: editions/2025-10-02-uk.html
   Audience: UK
   Subject: Join us for PolicyEngine 2.0 launch • 3 November in London

Reading HTML file...
✓ Read 11699 characters

Creating campaign...
✓ Campaign created (ID: 56788b0d71)

============================================================
✅ DRAFT CAMPAIGN CREATED SUCCESSFULLY
============================================================
Campaign ID: 56788b0d71
Web ID: 10142265
Audience: UK
Subject: Join us for PolicyEngine 2.0 launch • 3 November in London

🔗 Edit in Mailchimp:
   https://us5.admin.mailchimp.com/campaigns/edit?id=10142265

⚠️  This is a DRAFT - not sent yet. Review and send from Mailchimp.
```
