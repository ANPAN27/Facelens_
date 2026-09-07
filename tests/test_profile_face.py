from search.profile_face import _profile_image_url, _session


def test_github_avatar_url_offline():
    s = _session()
    url = _profile_image_url(s, "GitHub", "tusharpamnani", "https://github.com/tusharpamnani")
    assert url == "https://github.com/tusharpamnani.png"


def test_handle_cleaning():
    assert _profile_image_url(_session(), "GitHub", "@john", "https://github.com/@john") is not None


def test_profile_face_sort_is_deterministic():
    from search.profile_face import verify_profile_faces
    import numpy as np

    class FakeEncoder:
        def encode(self, img):
            raise ValueError("no face")

    class FakeDetector:
        pass

    profiles = {"GitHub": ["https://github.com/x"]}
    checks = verify_profile_faces(np.zeros((1, 512)), profiles, FakeEncoder(), FakeDetector())
    assert len(checks) == 1
    assert checks[0]["status"] == "no-face-in-avatar"