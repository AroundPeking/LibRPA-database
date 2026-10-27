"""Streaming and integrity regressions for the read-only MCP server."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("librpa_mcp_server", ROOT / "plugin/mcp/server.py")
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class ChunkedResponse:
    """A response that rejects unbounded read() calls."""

    def __init__(self, payload: bytes):
        self.stream = io.BytesIO(payload)
        self.read_sizes = []

    def read(self, size=-1):
        if size is None or size <= 0:
            raise AssertionError("payload response was read without a bounded chunk size")
        self.read_sizes.append(size)
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()


class PayloadStreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"LIBRPA_DB_CACHE_DIR": str(self.root / "cache")})
        self.env.start()
        self.payload = ("header\n" + "αβγδεζηθ\n" * 1000).encode()
        self.file = {
            "path": "data/calculations/3d/Si/test/logs/librpa.out",
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "size_bytes": len(self.payload),
            "tier": "referenced",
            "external_url": "https://huggingface.co/datasets/x/y/resolve/" + "a" * 40 + "/payload",
            "external_url_backup": "https://hf-mirror.com/datasets/x/y/resolve/" + "a" * 40 + "/payload",
        }

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
        server._catalog_cache.update(data=None, fetched=0.0)

    def test_primary_hash_mismatch_streams_to_mirror_and_atomically_caches(self):
        responses = []

        def fetch(request, timeout):
            payload = b"wrong primary bytes" if request.full_url == self.file["external_url"] else self.payload
            response = ChunkedResponse(payload)
            responses.append(response)
            return response

        with mock.patch.object(server.urllib.request, "urlopen", side_effect=fetch), \
                mock.patch.object(server.time, "sleep"), \
                mock.patch.object(server, "_fetch", side_effect=AssertionError("unbounded payload fetch")):
            cached = server._payload_path(self.file)
        self.assertEqual(cached.read_bytes(), self.payload)
        self.assertEqual(len(responses), 4)  # three bad-primary attempts, then one valid mirror
        self.assertTrue(all(response.read_sizes for response in responses))
        self.assertEqual(list(cached.parent.glob("*.part")), [])

    def test_corrupt_cache_is_replaced_by_verified_bytes(self):
        cache = server._cache_path(self.file)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"poisoned cache")
        with mock.patch.object(server.urllib.request, "urlopen",
                               return_value=ChunkedResponse(self.payload)):
            self.assertEqual(server._payload_path(self.file), cache)
        self.assertEqual(cache.read_bytes(), self.payload)

    def _declare_record(self, file):
        record = {"id": "test", "files": {"logs": [file]}}
        server._catalog_cache.update(data={"calculations": [record]}, fetched=server.time.time())
        return record

    def test_text_preview_uses_verified_cache_and_bounded_character_prefix(self):
        self._declare_record(self.file)
        cache = server._cache_path(self.file)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(self.payload)
        with mock.patch.object(server, "_payload_bytes", side_effect=AssertionError("whole-payload read")), \
                mock.patch.object(server.urllib.request, "urlopen", side_effect=AssertionError("network")):
            result = server.tool_read_file({"record_id": "test", "path": self.file["path"], "max_bytes": 12})
        expected = self.payload.decode()[:12]
        self.assertEqual(result["content"], expected)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["sha256_verified"])
        self.assertEqual(result["size_bytes"], len(self.payload))

    def test_binary_preview_returns_verified_cache_location_not_text(self):
        payload = b"abc\x00def" * 100
        self.file.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))
        self._declare_record(self.file)
        cache = server._cache_path(self.file)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(payload)
        result = server.tool_read_file({"record_id": "test", "path": self.file["path"], "max_bytes": 1})
        self.assertTrue(result["binary"])
        self.assertNotIn("content", result)
        self.assertEqual(result["cached_at"], str(cache))
        self.assertEqual(result["size_bytes"], len(payload))


class FileUrlTests(unittest.TestCase):
    def test_local_payload_url_percent_encodes_each_path_segment(self):
        file = {"path": "data/calculations/3d/Si/x/logs/α β%#1.dat"}
        with mock.patch.dict(os.environ, {"LIBRPA_DB_SITE_ROOT": "https://example.org/db"}):
            self.assertEqual(
                server._file_url(file),
                "https://example.org/db/data/calculations/3d/Si/x/logs/"
                "%CE%B1%20%CE%B2%25%231.dat")


if __name__ == "__main__":
    unittest.main()
