import io
import unittest

from classroom_hand_raise.shared.protocol import (
    ProtocolError,
    decode_frame,
    encode_frame,
    read_frame,
    write_frame,
)


class ProtocolTests(unittest.TestCase):
    def test_encode_decode_roundtrip_uses_length_prefixed_json(self):
        message = {
            "type": "help_request",
            "student_id": "stu-1",
            "text": "循环这里没有看懂",
            "screenshot": "abc123",
        }

        frame = encode_frame(message)

        self.assertGreater(len(frame), 4)
        self.assertEqual(decode_frame(frame), message)

    def test_decode_rejects_truncated_frame(self):
        frame = encode_frame({"type": "heartbeat"})

        with self.assertRaises(ProtocolError):
            decode_frame(frame[:-2])

    def test_stream_read_write_reads_exactly_one_frame(self):
        stream = io.BytesIO()

        write_frame(stream, {"type": "raise_hand", "student_id": "stu-1"})
        write_frame(stream, {"type": "lower_hand", "student_id": "stu-1"})
        stream.seek(0)

        self.assertEqual(read_frame(stream)["type"], "raise_hand")
        self.assertEqual(read_frame(stream)["type"], "lower_hand")


if __name__ == "__main__":
    unittest.main()
