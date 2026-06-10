import base64
import unittest

from PIL import Image

from classroom_hand_raise.shared.image_tools import compress_image_for_upload
from classroom_hand_raise.shared.classroom import ClassroomState
from classroom_hand_raise.shared.constants import MAX_SCREENSHOT_BYTES, MAX_SCREENSHOT_EDGE


class HelpRequestTests(unittest.TestCase):
    def make_png(self, size=(2200, 1200), color=(66, 120, 220)):
        image = Image.new("RGB", size, color)
        import io

        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def test_compress_image_limits_edge_and_size(self):
        payload = compress_image_for_upload(self.make_png())

        image_bytes = base64.b64decode(payload["screenshot"])
        self.assertLessEqual(len(image_bytes), MAX_SCREENSHOT_BYTES)
        self.assertEqual(payload["image_format"], "jpeg")
        self.assertLessEqual(payload["width"], MAX_SCREENSHOT_EDGE)
        self.assertLessEqual(payload["height"], MAX_SCREENSHOT_EDGE)

    def test_help_request_requires_text_or_screenshot(self):
        state = ClassroomState()
        student_id = state.join_student("张三", ("127.0.0.1", 50001))

        with self.assertRaises(ValueError):
            state.add_help_request(student_id, "", None)

    def test_help_request_is_stored_unread_with_text_and_optional_image(self):
        state = ClassroomState()
        student_id = state.join_student("张三", ("127.0.0.1", 50001))

        request = state.add_help_request(student_id, "这里不会", {"screenshot": "abc", "image_format": "jpeg"})

        self.assertFalse(request.handled)
        self.assertEqual(request.student_name, "张三")
        self.assertEqual(state.unread_help_count(), 1)

        state.mark_help_handled(request.request_id)
        self.assertEqual(state.unread_help_count(), 0)


if __name__ == "__main__":
    unittest.main()
