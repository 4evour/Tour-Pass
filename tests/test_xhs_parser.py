import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.xhs_parser import extract_xhs_url, is_allowed_xhs_url
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
    print("XHS parser URL extraction and host validation passed.")


if __name__ == "__main__":
    run_tests()
