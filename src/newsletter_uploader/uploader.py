"""Newsletter uploader for Mailchimp campaigns."""

from pathlib import Path
from typing import Dict, Optional

from .audience import AudienceType, get_segment_opts
from .hosting_links import check_no_hosting_links
from .mailchimp_client import MailchimpClient


class NewsletterUploader:
    """Upload newsletters to Mailchimp as draft campaigns."""

    def __init__(self, client: MailchimpClient):
        """
        Initialize newsletter uploader.

        Args:
            client: Configured Mailchimp client
        """
        self.client = client

    def upload(
        self,
        html_file: Path,
        audience: AudienceType,
        subject: str,
        preview_text: str,
        title: Optional[str] = None,
    ) -> Dict:
        """
        Upload newsletter HTML as a draft Mailchimp campaign.

        Args:
            html_file: Path to HTML file to upload
            audience: Target audience (UK, US, or ALL)
            subject: Email subject line
            preview_text: Preview text shown in inbox
            title: Optional internal campaign title (defaults to filename)

        Returns:
            Dict with campaign_id and web_id

        Raises:
            FileNotFoundError: If HTML file doesn't exist
            HostingLinkError: If the HTML links a hosting address such as
                *.vercel.app, before anything reaches Mailchimp
            Exception: If upload fails
        """
        # Read HTML file
        if not html_file.exists():
            raise FileNotFoundError(f"HTML file not found: {html_file}")

        html_content = html_file.read_text(encoding="utf-8")
        check_no_hosting_links(html_content, source=html_file.name)

        # Generate title from filename if not provided
        if title is None:
            title = html_file.stem

        # Get segment options for audience
        segment_opts = get_segment_opts(audience)

        # Create campaign
        campaign = self.client.create_campaign(
            subject=subject,
            preview_text=preview_text,
            title=title,
            segment_opts=segment_opts,
        )

        campaign_id = campaign["id"]
        web_id = campaign["web_id"]

        # Upload HTML content
        self.client.upload_content(campaign_id, html_content)

        return {
            "campaign_id": campaign_id,
            "web_id": web_id,
        }

    def update(
        self,
        campaign_id: str,
        html_file: Path,
        subject: Optional[str] = None,
        preview_text: Optional[str] = None,
        title: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> Dict:
        """
        Update an existing Mailchimp campaign.

        Args:
            campaign_id: Mailchimp campaign ID to update
            html_file: Path to HTML file to upload
            subject: Optional new email subject line
            preview_text: Optional new preview text
            title: Optional new internal campaign title

        Returns:
            Dict with campaign_id and web_id

        Raises:
            FileNotFoundError: If HTML file doesn't exist
            HostingLinkError: If the HTML links a hosting address such as
                *.vercel.app, before anything reaches Mailchimp
            Exception: If update fails
        """
        # Read HTML file
        if not html_file.exists():
            raise FileNotFoundError(f"HTML file not found: {html_file}")

        html_content = html_file.read_text(encoding="utf-8")
        check_no_hosting_links(html_content, source=html_file.name)

        # Update campaign settings if provided
        if subject or preview_text or title:
            self.client.update_campaign(
                campaign_id=campaign_id,
                subject=subject,
                preview_text=preview_text,
                title=title,
            )

        # Update HTML content
        self.client.upload_content(campaign_id, html_content)

        # Get campaign info to return web_id
        response = self.client._get_campaign(campaign_id)

        return {
            "campaign_id": campaign_id,
            "web_id": response["web_id"],
        }
