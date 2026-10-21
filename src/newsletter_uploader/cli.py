"""Command-line interface for newsletter uploader."""

import sys
from pathlib import Path

import click

from . import comparables
from .audience import AudienceType
from .mailchimp_client import MailchimpClient
from .uploader import NewsletterUploader


@click.command()
@click.argument("html_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--audience",
    type=click.Choice(["uk", "us", "all"], case_sensitive=False),
    help="Target audience: uk, us, or all. Required for new campaigns.",
)
@click.option("--subject", required=True, help="Email subject line")
@click.option("--preview", required=True, help="Preview text (shown in email inbox)")
@click.option(
    "--title",
    help="Internal campaign title (defaults to filename)",
)
@click.option(
    "--api-key",
    envvar="MAILCHIMP_API_KEY",
    help="Mailchimp API key (or set MAILCHIMP_API_KEY env var)",
)
@click.option(
    "--list-id",
    envvar="MAILCHIMP_LIST_ID",
    default="71ed1f89d8",
    help="Mailchimp list ID (or set MAILCHIMP_LIST_ID env var)",
)
@click.option(
    "--campaign-id",
    help="Update existing campaign instead of creating new one",
)
def main(html_file, audience, subject, preview, title, api_key, list_id, campaign_id):
    """
    Upload newsletter HTML to Mailchimp as a draft campaign.

    \b
    Examples:
      # UK subscribers only
      upload-newsletter editions/2025-10-01-uk.html \\
        --audience uk \\
        --subject "UK Happy Hour Tomorrow" \\
        --preview "Join us for drinks"

      # All non-UK subscribers
      upload-newsletter editions/2025-01-15-us.html \\
        --audience us \\
        --subject "New US Research" \\
        --preview "Latest policy analysis"

      # All subscribers
      upload-newsletter editions/2025-01-01-global.html \\
        --audience all \\
        --subject "Year in Review" \\
        --preview "Our 2024 impact"
    """
    # Validate API key
    if not api_key:
        click.echo(
            "Error: MAILCHIMP_API_KEY not found. "
            "Set it via --api-key or environment variable.",
            err=True,
        )
        sys.exit(1)

    # Validate audience is provided for new campaigns
    if not campaign_id and not audience:
        click.echo(
            "Error: --audience is required when creating a new campaign.",
            err=True,
        )
        sys.exit(1)

    # Fresh comparables before a push (Max, 2026-10-21): every analysis an
    # edition dated on or after the cutover links needs a recent comparables
    # search in the scorecard (newsletter_uploader/comparables.py).
    due, problems = comparables.run_check([html_file])
    if problems:
        click.echo("❌ Comparables are not fresh for this edition:", err=True)
        for problem in problems:
            click.echo(f"   {problem}", err=True)
        click.echo(comparables.HOW_TO_FIX, err=True)
        sys.exit(1)
    if due:
        click.echo("✓ Comparables are fresh for every analysis this edition links")

    # Create client and uploader
    if campaign_id:
        click.echo("📧 Updating Mailchimp draft campaign")
        click.echo(f"   Campaign ID: {campaign_id}")
    else:
        click.echo("📧 Creating Mailchimp draft campaign")
        click.echo(f"   Audience: {audience.upper()}")
    click.echo(f"   File: {html_file}")
    click.echo(f"   Subject: {subject}")
    click.echo()

    try:
        # Initialize client and uploader
        client = MailchimpClient(api_key=api_key, list_id=list_id)
        uploader = NewsletterUploader(client)

        # Upload newsletter
        click.echo("Reading HTML file...")
        html_content = html_file.read_text()
        click.echo(f"✓ Read {len(html_content)} characters")

        if campaign_id:
            # Update existing campaign
            click.echo("\nUpdating campaign...")
            result = uploader.update(
                campaign_id=campaign_id,
                html_file=html_file,
                subject=subject,
                preview_text=preview,
                title=title,
            )
            click.echo(f"✓ Campaign updated (ID: {campaign_id})")
            success_message = "✅ DRAFT CAMPAIGN UPDATED SUCCESSFULLY"
        else:
            # Create new campaign
            click.echo("\nCreating campaign...")
            audience_type = AudienceType(audience)
            result = uploader.upload(
                html_file=html_file,
                audience=audience_type,
                subject=subject,
                preview_text=preview,
                title=title,
            )
            click.echo(f"✓ Campaign created (ID: {result['campaign_id']})")
            success_message = "✅ DRAFT CAMPAIGN CREATED SUCCESSFULLY"

        result_campaign_id = result["campaign_id"]
        web_id = result["web_id"]

        # Display results
        click.echo("\n" + "=" * 60)
        click.echo(success_message)
        click.echo("=" * 60)
        click.echo(f"Campaign ID: {result_campaign_id}")
        click.echo(f"Web ID: {web_id}")
        if not campaign_id:
            click.echo(f"Audience: {audience.upper()}")
        click.echo(f"Subject: {subject}")

        # Extract datacenter from API key for URL
        datacenter = api_key.split("-")[-1]
        click.echo("\n🔗 Edit in Mailchimp:")
        click.echo(
            f"   https://{datacenter}.admin.mailchimp.com/campaigns/edit?id={web_id}"
        )
        click.echo(
            "\n⚠️  This is a DRAFT - not sent yet. Review and send from Mailchimp."
        )

    except FileNotFoundError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
