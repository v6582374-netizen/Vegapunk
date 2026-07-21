from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from vegapunk.mas.models.runtime import ImageContent, TextContent


VENDOR_ROOT = Path(__file__).resolve().parents[2] / "third_party/paper_orchestra"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

from utils import genai_types as types  # noqa: E402
from utils.gemini_utils import call_gemini_with_contents  # noqa: E402
from utils.vegapunk_adapter import call_responses_with_contents  # noqa: E402


class VendoredModelHelperTest(unittest.TestCase):
    def test_gemini_named_call_uses_responses_bridge(self) -> None:
        with patch(
            "utils.gemini_utils.call_responses_with_contents",
            return_value='```json\n{"candidates": []}\n```',
        ) as call:
            result = call_gemini_with_contents(
                contents=[types.Part.from_text(text="find real papers")],
                model_name="gemini-3-flash-preview",
            )

        self.assertEqual(result["parsed_response"], {"candidates": []})
        self.assertEqual(call.call_args.kwargs["model_name"], "gemini-3-flash-preview")

    def test_pdf_becomes_text_and_images_remain_image_inputs(self) -> None:
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Extracted paper body")
        pdf_bytes = document.tobytes()
        document.close()
        image_bytes = b"not-decoded-by-the-adapter"

        with patch(
            "utils.vegapunk_adapter.generate_text_from_environment",
            return_value="ok",
        ) as generate:
            response = call_responses_with_contents(
                contents=[
                    types.Part.from_bytes(
                        data=pdf_bytes, mime_type="application/pdf"
                    ),
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                ],
                model_name="gpt-5.6-sol",
            )

        self.assertEqual(response, "ok")
        content = generate.call_args.kwargs["content"]
        self.assertIsInstance(content[0], TextContent)
        self.assertIn("Extracted paper body", content[0].text)
        self.assertIsInstance(content[1], ImageContent)
        self.assertTrue(content[1].image_url.startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
