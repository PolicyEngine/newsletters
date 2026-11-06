"""Mailchimp API client for campaign management."""

import re
import unicodedata
from typing import Dict, Optional

import requests

# Mailchimp's limit for tracking.google_analytics.
GA_NAME_MAX = 50
GA_NAME_PREFIX = "pe-newsletter-"


def ga_campaign_name(title: str) -> str:
    """Google Analytics campaign name (utm_campaign) for a newsletter.

    Deterministic: the same title always gives the same name, so GA4 can
    group sends by edition. ``2026-10-26-uk`` gives
    ``pe-newsletter-2026-10-26-uk``. The result is at most 50 characters,
    Mailchimp's limit for the field.
    """
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    room = GA_NAME_MAX - len(GA_NAME_PREFIX)
    slug = slug[:room].rstrip("-") or "edition"
    return f"{GA_NAME_PREFIX}{slug}"


class MailchimpClient:
    """Client for interacting with Mailchimp API."""

    def __init__(self, api_key: str, list_id: str):
        """
        Initialize Mailchimp client.

        Args:
            api_key: Mailchimp API key (format: key-datacenter)
            list_id: Mailchimp list/audience ID
        """
        self.api_key = api_key
        self.list_id = list_id

        # Extract datacenter from API key (e.g., "us5" from "key-us5")
        datacenter = api_key.split("-")[-1]
        self.base_url = f"https://{datacenter}.api.mailchimp.com/3.0"

    def create_campaign(
        self,
        subject: str,
        preview_text: str,
        title: str,
        segment_opts: Optional[Dict] = None,
        from_name: str = "PolicyEngine",
        reply_to: str = "hello@policyengine.org",
        google_analytics: Optional[str] = None,
    ) -> Dict:
        """
        Create a new Mailchimp campaign.

        Google Analytics link tracking is always on: Mailchimp adds
        ``utm_campaign`` (and ``utm_source``/``utm_medium``) to every link,
        so GA4 attributes the visits to the edition.

        Args:
            subject: Email subject line
            preview_text: Preview text shown in inbox
            title: Internal campaign title
            segment_opts: Optional audience segment configuration
            from_name: Sender name
            reply_to: Reply-to email address
            google_analytics: GA campaign name (utm_campaign); defaults to
                ``ga_campaign_name(title)``

        Returns:
            Campaign data from Mailchimp API

        Raises:
            Exception: If campaign creation fails
        """
        campaign_data = {
            "type": "regular",
            "recipients": {"list_id": self.list_id},
            "settings": {
                "subject_line": subject,
                "preview_text": preview_text,
                "title": title,
                "from_name": from_name,
                "reply_to": reply_to,
                "auto_footer": False,
                "inline_css": False,
            },
            "tracking": {
                "opens": True,
                "html_clicks": True,
                "text_clicks": True,
                "google_analytics": google_analytics or ga_campaign_name(title),
            },
        }

        # Add segment if provided
        if segment_opts:
            campaign_data["recipients"]["segment_opts"] = segment_opts

        response = requests.post(
            f"{self.base_url}/campaigns",
            auth=("anystring", self.api_key),
            json=campaign_data,
        )

        if response.status_code != 200:
            raise Exception(
                f"Error creating campaign: {response.status_code}\n{response.text}"
            )

        return response.json()

    def upload_content(self, campaign_id: str, html_content: str) -> None:
        """
        Upload HTML content to a campaign.

        Args:
            campaign_id: Mailchimp campaign ID
            html_content: HTML content to upload

        Raises:
            Exception: If content upload fails
        """
        response = requests.put(
            f"{self.base_url}/campaigns/{campaign_id}/content",
            auth=("anystring", self.api_key),
            json={"html": html_content},
        )

        if response.status_code != 200:
            raise Exception(
                f"Error uploading content: {response.status_code}\n{response.text}"
            )

    def update_campaign(
        self,
        campaign_id: str,
        subject: Optional[str] = None,
        preview_text: Optional[str] = None,
        title: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> Dict:
        """
        Update campaign settings.

        Args:
            campaign_id: Mailchimp campaign ID
            subject: New email subject line (optional)
            preview_text: New preview text (optional)
            title: New internal campaign title (optional)
            from_name: New sender name (optional)

        Returns:
            Updated campaign data from Mailchimp API

        Raises:
            Exception: If campaign update fails
        """
        settings = {}
        if subject is not None:
            settings["subject_line"] = subject
        if preview_text is not None:
            settings["preview_text"] = preview_text
        if title is not None:
            settings["title"] = title
        if from_name is not None:
            settings["from_name"] = from_name

        update_data = {}
        if settings:
            update_data["settings"] = settings

        response = requests.patch(
            f"{self.base_url}/campaigns/{campaign_id}",
            auth=("anystring", self.api_key),
            json=update_data,
        )

        if response.status_code != 200:
            raise Exception(
                f"Error updating campaign: {response.status_code}\n{response.text}"
            )

        return response.json()

    def _get_campaign(self, campaign_id: str) -> Dict:
        """
        Get campaign details.

        Args:
            campaign_id: Mailchimp campaign ID

        Returns:
            Campaign data from Mailchimp API

        Raises:
            Exception: If request fails
        """
        response = requests.get(
            f"{self.base_url}/campaigns/{campaign_id}",
            auth=("anystring", self.api_key),
        )

        if response.status_code != 200:
            raise Exception(
                f"Error getting campaign: {response.status_code}\n{response.text}"
            )

        return response.json()
