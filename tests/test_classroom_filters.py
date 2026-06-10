import unittest

from classroom_hand_raise.shared.classroom import ClassroomState


class ClassroomFilterTests(unittest.TestCase):
    def test_help_request_filters_and_snapshot(self):
        state = ClassroomState()
        first = state.join_student("张三", ("127.0.0.1", 50001))
        second = state.join_student("李四", ("127.0.0.1", 50002))
        first_request = state.add_help_request(first, "第一题不会", None)
        second_request = state.add_help_request(second, "第二题不会", None)
        state.mark_help_handled(first_request.request_id)

        unread = state.help_requests(status="unread")
        handled = state.help_requests(status="handled")
        by_student = state.help_requests(student_id=second)
        snapshot = state.snapshot()

        self.assertEqual([item.request_id for item in unread], [second_request.request_id])
        self.assertEqual([item.request_id for item in handled], [first_request.request_id])
        self.assertEqual([item.request_id for item in by_student], [second_request.request_id])
        self.assertEqual(snapshot["unread_help_count"], 1)
        self.assertEqual(len(snapshot["help_requests"]), 2)


if __name__ == "__main__":
    unittest.main()
