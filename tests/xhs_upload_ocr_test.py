import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_multi_agent


def run_tests():
    async def check_invalid_image():
        original_token_getter = api_multi_agent._get_baidu_ocr_token

        async def fake_token():
            return "fake-token"

        api_multi_agent._get_baidu_ocr_token = fake_token
        try:
            try:
                await api_multi_agent._ocr_xhs_image_data_url("data:text/plain;base64,SGVsbG8=")
            except ValueError as exc:
                assert "图片格式不支持" in str(exc)
            else:
                raise AssertionError("Expected non-image data URL to be rejected")
        finally:
            api_multi_agent._get_baidu_ocr_token = original_token_getter

    asyncio.run(check_invalid_image())

    req = api_multi_agent.XhsParseRequest(link="", imageDataUrls=["data:image/png;base64,AA=="])
    assert req.imageDataUrls
    assert req.link == ""
    print("XHS uploaded image OCR validation passed.")


if __name__ == "__main__":
    run_tests()
