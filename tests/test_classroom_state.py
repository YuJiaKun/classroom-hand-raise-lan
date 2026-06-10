import unittest

from classroom_hand_raise.shared.classroom import ClassroomState
from classroom_hand_raise.shared.constants import FEEDBACK_OPTIONS


class ClassroomStateTests(unittest.TestCase):
    def test_students_can_join_raise_lower_and_leave(self):
        state = ClassroomState()

        student_id = state.join_student("张三", ("127.0.0.1", 50001))
        state.raise_hand(student_id)

        self.assertEqual([item.student_id for item in state.hand_queue()], [student_id])

        state.lower_hand(student_id)
        self.assertEqual(state.hand_queue(), [])

        state.leave_student(student_id)
        self.assertEqual(state.online_students(), [])

    def test_repeated_raise_keeps_original_queue_position(self):
        state = ClassroomState()
        first = state.join_student("张三", ("127.0.0.1", 50001))
        second = state.join_student("李四", ("127.0.0.1", 50002))

        state.raise_hand(first)
        state.raise_hand(second)
        state.raise_hand(first)

        self.assertEqual([item.student_id for item in state.hand_queue()], [first, second])

    def test_feedback_counts_are_updated_per_student_latest_state(self):
        state = ClassroomState()
        first = state.join_student("张三", ("127.0.0.1", 50001))
        second = state.join_student("李四", ("127.0.0.1", 50002))

        state.set_feedback(first, "我没听懂")
        state.set_feedback(second, "我没听懂")
        state.set_feedback(first, "可以继续")

        self.assertEqual(state.feedback_summary(), {"可以继续": 1, "我没听懂": 1})

    def test_same_client_id_reuses_student_and_preserves_classroom_state(self):
        state = ClassroomState()
        first = state.join_student("张三", ("127.0.0.1", 50001), client_id="client-a", connection_id="conn-1")
        state.raise_hand(first)
        state.set_feedback(first, "我没听懂")

        second = state.join_student("张三新连接", ("127.0.0.1", 50002), client_id="client-a", connection_id="conn-2")
        snapshot = state.snapshot()

        self.assertEqual(second, first)
        self.assertEqual(snapshot["online_count"], 1)
        self.assertEqual(len(snapshot["students"]), 1)
        self.assertEqual(snapshot["students"][0]["name"], "张三新连接")
        self.assertEqual(snapshot["students"][0]["address"], ("127.0.0.1", 50002))
        self.assertEqual(snapshot["students"][0]["online"], True)
        self.assertEqual(snapshot["students"][0]["active_connection_id"], "conn-2")
        self.assertEqual(len(state.hand_queue()), 1)
        self.assertEqual(state.feedback_summary(), {"我没听懂": 1})

    def test_offline_student_stays_in_snapshot_but_not_online_counts(self):
        state = ClassroomState()
        student_id = state.join_student("张三", ("127.0.0.1", 50001), client_id="client-a", connection_id="conn-1")
        state.raise_hand(student_id)
        state.set_feedback(student_id, "讲慢一点")

        self.assertTrue(state.mark_student_offline(student_id, connection_id="conn-1"))
        snapshot = state.snapshot()

        self.assertEqual(snapshot["online_count"], 0)
        self.assertEqual(len(snapshot["students"]), 1)
        self.assertEqual(snapshot["students"][0]["online"], False)
        self.assertEqual(snapshot["students"][0]["connection_status"], "离线")
        self.assertEqual(snapshot["hand_count"], 0)
        self.assertEqual(snapshot["feedback_summary"], {})

    def test_stale_connection_cannot_mark_new_connection_offline(self):
        state = ClassroomState()
        student_id = state.join_student("张三", ("127.0.0.1", 50001), client_id="client-a", connection_id="conn-1")
        same_student_id = state.join_student("张三", ("127.0.0.1", 50002), client_id="client-a", connection_id="conn-2")

        self.assertEqual(same_student_id, student_id)
        self.assertFalse(state.mark_student_offline(student_id, connection_id="conn-1"))
        self.assertEqual(state.snapshot()["online_count"], 1)
        self.assertTrue(state.mark_student_offline(student_id, connection_id="conn-2"))
        self.assertEqual(state.snapshot()["online_count"], 0)

    def test_feedback_options_are_classroom_action_labels(self):
        self.assertEqual(
            FEEDBACK_OPTIONS,
            ("可以继续", "我没听懂", "讲慢一点", "请再讲一遍"),
        )


if __name__ == "__main__":
    unittest.main()
