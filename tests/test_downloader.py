"""
Unit tests for URL validation and YouTube downloader.
"""

import pytest
from src.config import DubbingConfig
from src.downloader import Downloader, extract_video_id, validate_youtube_url
from src.utils import sanitize_filename


def test_validate_youtube_url_valid():
    valid_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "http://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://youtube.com/embed/dQw4w9WgXcQ",
    ]
    for url in valid_urls:
        assert validate_youtube_url(url) is True, f"Failed for valid URL: {url}"


def test_validate_youtube_url_invalid():
    invalid_urls = [
        "https://example.com/video.mp4",
        "https://vimeo.com/123456",
        "not_a_url",
        "",
        "https://youtube.com/feed/subscriptions",
    ]
    for url in invalid_urls:
        assert validate_youtube_url(url) is False, f"Failed for invalid URL: {url}"


def test_extract_video_id():
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://www.youtube.com/shorts/abcd1234efg") == "abcd1234efg"
    assert extract_video_id("invalid") is None


def test_sanitize_filename():
    unsafe_name = 'Video: "Sample" / Test & More? <Yes> | *No*'
    safe_name = sanitize_filename(unsafe_name)
    assert ":" not in safe_name
    assert '"' not in safe_name
    assert "/" not in safe_name
    assert "?" not in safe_name
    assert "<" not in safe_name
    assert ">" not in safe_name
    assert "|" not in safe_name
    assert "*" not in safe_name
    assert safe_name == "Video_Sample_Test_&_More_Yes_No"


def test_downloader_rejects_invalid_url(tmp_path):
    config = DubbingConfig(download_dir=tmp_path)
    downloader = Downloader(config)
    with pytest.raises(ValueError, match="Invalid YouTube URL"):
        downloader.download("https://invalid-url.com")
