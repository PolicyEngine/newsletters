# PolicyEngine Newsletter Repository

This repository contains HTML templates for PolicyEngine newsletters sent via Mailchimp.

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

1. Set your Mailchimp API key:
```bash
export MAILCHIMP_API_KEY="your-key-us5"
```

2. Create a newsletter HTML file in `editions/` (e.g., `2025-10-01-uk.html`)

3. Upload to Mailchimp as a draft:
```bash
upload-newsletter editions/2025-10-01-uk.html \
  --audience uk \
  --subject "Your Subject Line" \
  --preview "Preview text shown in inbox"
```

4. Review the draft in Mailchimp and send when ready

## Audience Targeting

- `--audience uk` - UK subscribers only
- `--audience us` - All non-UK subscribers (includes US and missing country data)
- `--audience all` - All subscribers

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=newsletter_uploader --cov-report=term-missing

# Format code
black src/ tests/

# Lint code
ruff check src/ tests/
```

## Package Structure

- `src/newsletter_uploader/` - Python package
  - `mailchimp_client.py` - Mailchimp API client
  - `audience.py` - Audience targeting logic
  - `uploader.py` - Newsletter uploader
  - `cli.py` - Command-line interface
- `tests/` - pytest suite
- `editions/` - Newsletter HTML files
- `.env` - Contains `MAILCHIMP_API_KEY` (gitignored)
