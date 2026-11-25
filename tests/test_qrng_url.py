import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import gspread
import requests
import streamlit as st
from google.oauth2 import service_account
from PIL import Image
from streamlit.testing.v1 import AppTest

from utils import qrng_helper as helper


class QRNGURLTests(unittest.TestCase):
    def setUp(self):
        helper._resolve_base_url_from_sheet.clear()
        self.addCleanup(helper._resolve_base_url_from_sheet.clear)
        self.sheet = Mock()
        self.sheet.acell.side_effect = lambda cell: Mock(value=self.cells.get(cell))
        self.cells = {}
        self.client = Mock()
        self.client.open.return_value.worksheet.return_value = self.sheet
        patches = [
            patch.object(st, "secrets", {"gcp": {"test": "mock"}}),
            patch.object(service_account.Credentials, "from_service_account_info"),
            patch.object(gspread, "authorize", return_value=self.client),
            patch.object(requests, "get"),
            patch.object(requests, "post"),
            patch.object(st, "warning"),
        ]
        for p in patches:
            self.addCleanup(p.stop)
        self.secrets, self.creds, self.authorize, self.get, self.post, self.warning = [p.start() for p in patches]
        self.post.side_effect = self.valid_post

    def valid_post(self, url, *, json, timeout):
        response = Mock()
        response.json.return_value = {"bits": "0" * json["n_bits"]}
        return response

    def test_a2_wins_over_broken_legacy_url(self):
        self.cells.update(A2=" https://direct.example/ ", A1="https://old.example/ngrok-url")
        self.get.side_effect = requests.HTTPError("404")
        self.assertEqual(helper.get_qrng_bits_with_source(32768), ("0" * 32768, True))
        self.sheet.acell.assert_called_once_with("A2")
        self.get.assert_not_called()
        self.post.assert_called_once_with("https://direct.example/get_bits/", json={"n_bits": 32768}, timeout=20)
        self.warning.assert_not_called()

    def test_a1_legacy_redirect(self):
        self.cells.update(A2="", A1="https://old.example/ngrok-url/")
        self.get.return_value.text = " https://direct.example/ "
        self.assertEqual(helper.get_qrng_bits_with_source(8), ("0" * 8, True))
        self.get.assert_called_once_with("https://old.example/ngrok-url", timeout=5)

    def test_a1_direct_url(self):
        self.cells.update(A2="invalid", A1="https://direct.example/")
        self.assertEqual(helper.get_qrng_bits_from_api(8), "0" * 8)
        self.get.assert_not_called()

    def test_exact_legacy_404_falls_back(self):
        self.cells.update(A2="", A1="https://old.example/ngrok-url")
        self.get.return_value.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        bits, qrng = helper.get_qrng_bits_with_source(32768)
        self.assertEqual(len(bits), 32768)
        self.assertLessEqual(set(bits), {"0", "1"})
        self.assertFalse(qrng)
        self.warning.assert_called()
        self.post.assert_not_called()

    def test_missing_gcp_config_falls_back(self):
        self.secrets.clear()
        bits, qrng = helper.get_qrng_bits_with_source(64)
        self.assertEqual(len(bits), 64)
        self.assertFalse(qrng)
        self.post.assert_not_called()

    def test_sheet_failure_falls_back(self):
        self.authorize.side_effect = RuntimeError("Sheet offline")
        bits, qrng = helper.get_qrng_bits_with_source(64)
        self.assertEqual(len(bits), 64)
        self.assertFalse(qrng)
        self.post.assert_not_called()

    def test_post_failure_falls_back(self):
        self.cells["A2"] = "https://direct.example"
        self.post.side_effect = requests.Timeout()
        bits, qrng = helper.get_qrng_bits_with_source(64)
        self.assertEqual(len(bits), 64)
        self.assertFalse(qrng)

    def test_invalid_response_falls_back(self):
        self.cells["A2"] = "https://direct.example"
        for response in ({"bits": "1"}, {"bits": "0000x000"}, {"bits": None}, {}):
            with self.subTest(response=response):
                self.post.side_effect = None
                self.post.return_value.json.return_value = response
                bits, qrng = helper.get_qrng_bits_with_source(8)
                self.assertFalse(qrng)
                self.assertEqual(len(bits), 8)
                self.assertLessEqual(set(bits), {"0", "1"})

    def test_large_particle_request(self):
        self.cells["A2"] = "https://direct.example"
        n = 8 * 18000 * 8
        bits, qrng = helper.get_qrng_bits_with_source(n)
        self.assertTrue(qrng)
        self.assertEqual(len(int(bits, 2).to_bytes(n // 8, "big")), n // 8)


class ArtIntegrationTests(unittest.TestCase):
    def generate(self, mode, *, fail_after=None):
        calls = []
        def post(url, *, json, timeout):
            calls.append(json["n_bits"])
            if fail_after is not None and len(calls) > fail_after:
                raise requests.Timeout("mock QRNG offline")
            response = Mock()
            n = json["n_bits"]
            response.json.return_value = {"bits": ("00101101" * ((n + 7) // 8))[:n]}
            return response

        with patch.object(helper, "_resolve_base_url_from_sheet", return_value="https://direct.example"), \
             patch.object(requests, "post", side_effect=post), \
             patch.object(st, "image") as image, \
             patch.object(st, "download_button") as download:
            at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main_page.py"), default_timeout=60).run()
            self.assertEqual(len(at.exception), 0, str(at.exception))
            at.number_input[0].set_value(512)
            at.number_input[1].set_value(512)
            at.slider[0].set_value(1000)
            at.slider[1].set_value(20)
            at.radio[0].set_value(mode)
            at.button[0].click().run(timeout=60)
            self.assertEqual(len(at.exception), 0, str(at.exception))
            self.assertEqual(image.call_count, 2 if mode.startswith("Compare") else 1)
            self.assertEqual(download.call_count, image.call_count)
            names = []
            captions = []
            for call, image_call in zip(download.call_args_list, image.call_args_list):
                names.append(call.kwargs["file_name"])
                captions.append(image_call.kwargs["caption"])
                with Image.open(io.BytesIO(call.kwargs["data"])) as png:
                    self.assertEqual(png.size, (512, 512))
                    self.assertEqual(png.format, "PNG")
            return names, captions, calls

    def test_qrng_generates_real_png(self):
        names, captions, calls = self.generate("QRNG")
        self.assertTrue(names[0].startswith("qrng_art_"))
        self.assertIn("QRNG", captions[0])
        self.assertEqual(calls[0], 32768)

    def test_qrng_partial_fallback_is_labeled(self):
        names, captions, calls = self.generate("QRNG", fail_after=1)
        self.assertTrue(names[0].startswith("qrng_fallback_art_"))
        self.assertIn("local PRNG fallback used", captions[0])

    def test_prng_does_not_contact_qrng(self):
        names, captions, calls = self.generate("PRNG")
        self.assertTrue(names[0].startswith("prng_art_"))
        self.assertEqual(calls, [])

    def test_compare_mode_handles_qrng_outage(self):
        names, captions, calls = self.generate("Compare QRNG vs PRNG", fail_after=0)
        self.assertTrue(names[0].startswith("qrng_fallback_art_"))
        self.assertTrue(names[1].startswith("prng_art_"))
        self.assertIn("local PRNG fallback used", captions[0])
