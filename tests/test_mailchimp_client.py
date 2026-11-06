"""Tests for Mailchimp client."""

import json

import pytest
import responses

from newsletter_uploader.mailchimp_client import (
    GA_NAME_MAX,
    MailchimpClient,
    ga_campaign_name,
)


@pytest.fixture
def client():
    """Create a Mailchimp client for testing."""
    return MailchimpClient(api_key="test-key-us5", list_id="test-list-id")


class TestMailchimpClient:
    """Test MailchimpClient class."""

    def test_client_initialization(self, client):
        """Test client initializes with correct values."""
        assert client.api_key == "test-key-us5"
        assert client.list_id == "test-list-id"
        assert client.base_url == "https://us5.api.mailchimp.com/3.0"

    def test_client_extracts_datacenter_from_key(self):
        """Test datacenter extraction from API key."""
        client = MailchimpClient(api_key="test-key-us10", list_id="list-id")
        assert client.base_url == "https://us10.api.mailchimp.com/3.0"

    @responses.activate
    def test_create_campaign_success(self, client):
        """Test successful campaign creation."""
        responses.post(
            "https://us5.api.mailchimp.com/3.0/campaigns",
            json={
                "id": "campaign123",
                "web_id": 12345,
                "recipients": {"recipient_count": 100},
            },
            status=200,
        )

        campaign = client.create_campaign(
            subject="Test Subject",
            preview_text="Test Preview",
            title="Test Campaign",
            segment_opts=None,
        )

        assert campaign["id"] == "campaign123"
        assert campaign["web_id"] == 12345
        assert len(responses.calls) == 1

        # Verify request payload
        request_body = responses.calls[0].request.body
        assert b"Test Subject" in request_body
        assert b"Test Preview" in request_body

    @responses.activate
    def test_create_campaign_with_segment(self, client):
        """Test campaign creation with audience segment."""
        responses.post(
            "https://us5.api.mailchimp.com/3.0/campaigns",
            json={"id": "campaign123", "web_id": 12345},
            status=200,
        )

        segment_opts = {
            "match": "all",
            "conditions": [{"field": "COUNTRY", "op": "is", "value": "United Kingdom"}],
        }

        campaign = client.create_campaign(
            subject="UK Test",
            preview_text="Preview",
            title="UK Campaign",
            segment_opts=segment_opts,
        )

        assert campaign["id"] == "campaign123"
        # Verify segment was included in request
        request_body = responses.calls[0].request.body
        assert b"segment_opts" in request_body

    @responses.activate
    def test_upload_content_success(self, client):
        """Test successful HTML content upload."""
        responses.put(
            "https://us5.api.mailchimp.com/3.0/campaigns/campaign123/content",
            json={"html": "<html>Test</html>"},
            status=200,
        )

        client.upload_content("campaign123", "<html>Test</html>")

        assert len(responses.calls) == 1
        request_body = responses.calls[0].request.body
        assert b"<html>Test</html>" in request_body

    @responses.activate
    def test_upload_content_failure(self, client):
        """Test content upload handles errors."""
        responses.put(
            "https://us5.api.mailchimp.com/3.0/campaigns/campaign123/content",
            json={"error": "Invalid campaign"},
            status=404,
        )

        with pytest.raises(Exception, match="Error uploading content"):
            client.upload_content("campaign123", "<html>Test</html>")

    @responses.activate
    def test_create_campaign_failure(self, client):
        """Test campaign creation handles errors."""
        responses.post(
            "https://us5.api.mailchimp.com/3.0/campaigns",
            json={"error": "Invalid list ID"},
            status=400,
        )

        with pytest.raises(Exception, match="Error creating campaign"):
            client.create_campaign(
                subject="Test",
                preview_text="Preview",
                title="Campaign",
                segment_opts=None,
            )


class TestGoogleAnalyticsTracking:
    """Every created campaign has Google Analytics link tracking on."""

    def test_ga_name_from_edition_title(self):
        assert ga_campaign_name("2026-10-26-uk") == "pe-newsletter-2026-10-26-uk"

    def test_ga_name_is_slugged_and_within_limit(self):
        name = ga_campaign_name("Autumn Budget: réforme " * 10)
        assert name.startswith("pe-newsletter-autumn-budget-reforme")
        assert len(name) <= GA_NAME_MAX
        assert not name.endswith("-")

    def test_ga_name_falls_back_for_empty_slug(self):
        assert ga_campaign_name("!!!") == "pe-newsletter-edition"

    @responses.activate
    def test_create_campaign_turns_on_ga_tracking(self, client):
        responses.post(
            "https://us5.api.mailchimp.com/3.0/campaigns",
            json={"id": "campaign123"},
            status=200,
        )

        client.create_campaign(subject="S", preview_text="P", title="2026-11-10-us")

        body = json.loads(responses.calls[0].request.body)
        assert body["tracking"]["google_analytics"] == "pe-newsletter-2026-11-10-us"
        assert body["tracking"]["html_clicks"] is True
        assert body["tracking"]["opens"] is True

    @responses.activate
    def test_create_campaign_accepts_explicit_ga_name(self, client):
        responses.post(
            "https://us5.api.mailchimp.com/3.0/campaigns",
            json={"id": "campaign123"},
            status=200,
        )

        client.create_campaign(
            subject="S",
            preview_text="P",
            title="Anything",
            google_analytics="pe-webinar-cpid",
        )

        body = json.loads(responses.calls[0].request.body)
        assert body["tracking"]["google_analytics"] == "pe-webinar-cpid"
