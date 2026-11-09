# Claude Code Configuration

Custom subagents and slash commands for PolicyEngine newsletter management.

## Subagents

### newsletter-writer
Converts PolicyEngine research posts into email-compatible newsletter HTML sections.

**Usage:**
- Automatically invoked when creating newsletter sections
- Reads markdown research posts
- Generates styled HTML with key findings
- Maintains brand colors and email compatibility

**Example:**
```
Use newsletter-writer to create a section for uk-carbon-tax-dividend.md
```

### campaign-analyzer
Analyzes Mailchimp campaign performance and provides data-driven recommendations.

**Usage:**
- Fetches campaign statistics from Mailchimp API
- Identifies performance trends
- Suggests optimization strategies

**Example:**
```
Use campaign-analyzer to analyze our last 6 months of newsletters
```

### newsletter-previewer
Opens newsletter HTML in browser, captures screenshots, and validates email compatibility.

**Usage:**
- Opens HTML in browser for visual review
- Takes screenshots at desktop (600px) and mobile (320px) widths
- Validates email client compatibility
- Checks links and images

**Example:**
```
Use newsletter-previewer to preview editions/2025-10-02-uk.html
```

## Slash Commands

### /create-newsletter
Generate a complete newsletter from blog posts and events.

```bash
/create-newsletter --posts uk-carbon-tax,uk-vat --event nov-3-london --audience uk
```

Creates a new HTML file in `editions/` with:
- Event hero section (if --event provided)
- Research sections from blog posts
- Proper styling and email compatibility

### /campaign-stats
Quick campaign performance stats by date.

```bash
/campaign-stats 2024-10-29
```

Shows:
- Open and click rates
- Top performing links
- Comparison to averages

### /sync-countries
Sync subscriber COUNTRY field from Mailchimp predicted location.

```bash
/sync-countries
```

Updates subscribers who don't have COUNTRY set by syncing from Mailchimp's predicted location data.

### /upload-draft
Upload newsletter to Mailchimp as draft campaign.

```bash
/upload-draft editions/2025-10-02-uk.html --audience uk --subject "..." --preview "..."
```

Wrapper around `upload-newsletter` command with validation and helpful output.

### /preview-newsletter
Preview newsletter with screenshots and validation.

```bash
/preview-newsletter editions/2025-10-02-uk.html
```

Opens HTML in browser, captures screenshots at different viewport sizes, and validates email compatibility.

## File Structure

```
.claude/
├── agents/
│   ├── newsletter-writer.md
│   ├── campaign-analyzer.md
│   └── newsletter-previewer.md
├── commands/
│   ├── create-newsletter.md
│   ├── campaign-stats.md
│   ├── sync-countries.md
│   ├── upload-draft.md
│   └── preview-newsletter.md
└── README.md (this file)
```

## Adding New Commands

1. Create `.md` file in `.claude/commands/`
2. Add YAML frontmatter with description and argument hints
3. Write command documentation/instructions
4. Command name = filename without `.md`

## Adding New Subagents

1. Create `.md` file in `.claude/agents/`
2. Add YAML frontmatter with name, description, and tools
3. Write detailed system prompt for the subagent
4. Subagent will be invoked automatically when matching its description
