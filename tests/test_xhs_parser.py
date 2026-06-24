import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.xhs_parser import extract_xhs_url, fetch_note_ssr, is_allowed_xhs_url
import api_multi_agent


def run_tests():
    assert extract_xhs_url("看看 https://www.xiaohongshu.com/explore/65abc123def45678901234?xsec=1") == (
        "https://www.xiaohongshu.com/explore/65abc123def45678901234?xsec=1"
    )
    assert extract_xhs_url("xhslink.com/abc123，复制") == "https://xhslink.com/abc123"
    assert extract_xhs_url("https://example.com/explore/65abc123def456") is None
    assert not is_allowed_xhs_url("http://127.0.0.1:8000/private")
    assert not is_allowed_xhs_url("https://xiaohongshu.com.evil.test/explore/abc")
    assert is_allowed_xhs_url("https://www.xiaohongshu.com/explore/abc")
    assert is_allowed_xhs_url("https://xhslink.com/abc")
    assert api_multi_agent._is_allowed_xhs_image_url("https://sns-img-qc.xhscdn.com/pic.jpg")
    assert api_multi_agent._is_allowed_xhs_image_url("https://example.xhscdn.com/pic.jpg")
    assert not api_multi_agent._is_allowed_xhs_image_url("http://127.0.0.1:8080/pic.jpg")
    assert not api_multi_agent._is_allowed_xhs_image_url("https://www.xiaohongshu.com/explore/abc")

    class FakeResponse:
        text = "<html><head><title>小红书 - 你访问的页面不见了</title></head><body></body></html>"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    import tools.xhs_parser as xhs_parser
    original_xhs_client = xhs_parser.httpx.Client
    xhs_parser.httpx.Client = FakeClient
    try:
        try:
            fetch_note_ssr("6a16b2840000000035030fc6")
        except ValueError as exc:
            assert "无法读取正文" in str(exc)
        else:
            raise AssertionError("Expected unavailable XHS page to raise a clear ValueError")
    finally:
        xhs_parser.httpx.Client = original_xhs_client
    print("XHS parser URL extraction and host validation passed.")


if __name__ == "__main__":
    run_tests()
