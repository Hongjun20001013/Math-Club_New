import unittest

from placement_english_ui import placement_track_for_topic
from placement_public import ADVISOR_PRESETS, counselor_names_for_staff_username


class TestPlacementAdvisorTeam(unittest.TestCase):
    def test_team_advisors_on_intake(self) -> None:
        self.assertEqual(
            ADVISOR_PRESETS,
            ("Mia Hu", "Jimmy Zheng", "Beck Yang", "Ling Zhang", "Lily"),
        )

    def test_staff_username_maps_to_counselor_label(self) -> None:
        self.assertEqual(counselor_names_for_staff_username("Mia@novelprep.org"), ("Mia Hu",))
        self.assertEqual(counselor_names_for_staff_username("beck.yang@novelprep.org"), ("Beck Yang",))
        self.assertEqual(counselor_names_for_staff_username("ling.zhang@novelprep.org"), ("Ling Zhang",))
        self.assertEqual(counselor_names_for_staff_username("lily@novelprep.org"), ("Lily",))

    def test_placement_track_split(self) -> None:
        self.assertEqual(placement_track_for_topic("english_g7_8"), "english")
        self.assertEqual(placement_track_for_topic("enhanced_math_1"), "math")


if __name__ == "__main__":
    unittest.main()
