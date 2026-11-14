"""Tests for newsletter uploader."""

from pathlib import Path

import pytest

from newsletter_uploader.audience import AudienceType
from newsletter_uploader.hosting_links import HostingLinkError
from newsletter_uploader.uploader import NewsletterUploader


@pytest.fixture
def mock_client(mocker):
    """Create a mock Mailchimp client."""
    return mocker.MagicMock()


@pytest.fixture
def uploader(mock_client):
    """Create a newsletter uploader with mock client."""
    return NewsletterUploader(mock_client)


@pytest.fixture
def html_file(tmp_path):
    """Create a temporary HTML file for testing."""
    html_path = tmp_path / "test_newsletter.html"
    html_path.write_text("<html><body>Test Newsletter</body></html>")
    return html_path


class TestNewsletterUploader:
    """Test NewsletterUploader class."""

    def test_upload_newsletter_uk_audience(self, uploader, mock_client, html_file):
        """Test uploading newsletter to UK audience."""
        mock_client.create_campaign.return_value = {
            "id": "campaign123",
            "web_id": 12345,
        }

        result = uploader.upload(
            html_file=html_file,
            audience=AudienceType.UK,
            subject="UK Newsletter",
            preview_text="Preview",
            title="Test Campaign",
        )

        assert result["campaign_id"] == "campaign123"
        assert result["web_id"] == 12345

        # Verify campaign was created with correct segment
        mock_client.create_campaign.assert_called_once()
        call_kwargs = mock_client.create_campaign.call_args[1]
        assert call_kwargs["subject"] == "UK Newsletter"
        assert call_kwargs["segment_opts"] is not None
        assert call_kwargs["segment_opts"]["conditions"][0]["value"] == "United Kingdom"

        # Verify content was uploaded
        mock_client.upload_content.assert_called_once_with(
            "campaign123", "<html><body>Test Newsletter</body></html>"
        )

    def test_upload_newsletter_us_audience(self, uploader, mock_client, html_file):
        """Test uploading newsletter to US (non-UK) audience."""
        mock_client.create_campaign.return_value = {
            "id": "campaign456",
            "web_id": 67890,
        }

        result = uploader.upload(
            html_file=html_file,
            audience=AudienceType.US,
            subject="US Newsletter",
            preview_text="Preview",
            title="US Campaign",
        )

        assert result["campaign_id"] == "campaign456"

        # Verify segment uses "not" operator for non-UK
        call_kwargs = mock_client.create_campaign.call_args[1]
        assert call_kwargs["segment_opts"]["conditions"][0]["op"] == "not"

    def test_upload_newsletter_all_audience(self, uploader, mock_client, html_file):
        """Test uploading newsletter to all subscribers."""
        mock_client.create_campaign.return_value = {
            "id": "campaign789",
            "web_id": 11111,
        }

        uploader.upload(
            html_file=html_file,
            audience=AudienceType.ALL,
            subject="Global Newsletter",
            preview_text="Preview",
            title="Global Campaign",
        )

        # Verify no segment filtering
        call_kwargs = mock_client.create_campaign.call_args[1]
        assert call_kwargs["segment_opts"] is None

    def test_upload_newsletter_file_not_found(self, uploader):
        """Test uploading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            uploader.upload(
                html_file=Path("nonexistent.html"),
                audience=AudienceType.UK,
                subject="Test",
                preview_text="Preview",
                title="Test",
            )

    def test_upload_newsletter_default_title(self, uploader, mock_client, html_file):
        """Test title defaults to filename if not provided."""
        mock_client.create_campaign.return_value = {
            "id": "campaign999",
            "web_id": 22222,
        }

        uploader.upload(
            html_file=html_file,
            audience=AudienceType.UK,
            subject="Test",
            preview_text="Preview",
        )

        call_kwargs = mock_client.create_campaign.call_args[1]
        assert call_kwargs["title"] == "test_newsletter"

    def test_upload_handles_campaign_creation_error(
        self, uploader, mock_client, html_file
    ):
        """Test upload handles campaign creation errors."""
        mock_client.create_campaign.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            uploader.upload(
                html_file=html_file,
                audience=AudienceType.UK,
                subject="Test",
                preview_text="Preview",
            )

        # Content upload should not be called if campaign creation fails
        mock_client.upload_content.assert_not_called()

    def test_upload_handles_content_upload_error(
        self, uploader, mock_client, html_file
    ):
        """Test upload handles content upload errors."""
        mock_client.create_campaign.return_value = {
            "id": "campaign123",
            "web_id": 12345,
        }
        mock_client.upload_content.side_effect = Exception("Upload Error")

        with pytest.raises(Exception, match="Upload Error"):
            uploader.upload(
                html_file=html_file,
                audience=AudienceType.UK,
                subject="Test",
                preview_text="Preview",
            )

    @pytest.mark.parametrize("method", ["upload", "update"])
    def test_hosting_link_stops_before_mailchimp(
        self, uploader, mock_client, tmp_path, method
    ):
        """An edition linking a hosting address never reaches Mailchimp."""
        html_path = tmp_path / "2026-11-03-us.html"
        html_path.write_text(
            '<html><body><a href="https://ballot-measures-2026.vercel.app/us/x">'
            "Dashboard</a></body></html>"
        )

        with pytest.raises(HostingLinkError, match="ballot-measures-2026.vercel.app"):
            if method == "upload":
                uploader.upload(
                    html_file=html_path,
                    audience=AudienceType.US,
                    subject="Test",
                    preview_text="Preview",
                )
            else:
                uploader.update(campaign_id="campaign123", html_file=html_path)

        assert mock_client.mock_calls == []

    @pytest.mark.parametrize("method", ["upload", "update"])
    @pytest.mark.parametrize("field", ["subject", "preview_text", "title"])
    def test_hosting_link_in_campaign_text_stops_before_mailchimp(
        self, uploader, mock_client, html_file, method, field
    ):
        """A hosting address in the subject, preview or title stops the upload."""
        text = {"subject": "Test", "preview_text": "Preview", "title": None}
        text[field] = "See x.vercel\u3002app now"

        with pytest.raises(HostingLinkError, match="x.vercel.app"):
            if method == "upload":
                uploader.upload(html_file=html_file, audience=AudienceType.US, **text)
            else:
                uploader.update(campaign_id="campaign123", html_file=html_file, **text)

        assert mock_client.mock_calls == []
