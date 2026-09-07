from datetime import datetime, timezone
from utils.hashing import compute_record_hash


class VerificationResult:
    def __init__(self, input_image_hash: str, results: list[dict], model: str = "ArcFace"):
        self.input_image_hash = input_image_hash
        self.results = results
        self.model = model
        self.timestamp = int(datetime.now(timezone.utc).timestamp())
        self.faces_detected = 1
        self.record_hash = ""
        self.blockchain = None
        self.social_profiles: dict = {}
        self.profile_face_checks: list = []

        self._compute_hash()

    def _compute_hash(self):
        candidate_hash = ""
        similarity = 0.0
        result_type = "NO_MATCH"

        if self.results:
            top = self.results[0]
            similarity = top.get("face_similarity", 0.0)
            result_type = f"{top.get('classification', 'LOW')}_SIMILARITY"
            candidate_hash = top.get("url", "")

        self.record_hash = compute_record_hash(
            self.input_image_hash, candidate_hash, similarity, result_type, self.timestamp
        )

    def set_blockchain(self, network: str, transaction: str):
        self.blockchain = {"network": network, "transaction": transaction}

    def to_dict(self) -> dict:
        return {
            "input_image_hash": self.input_image_hash,
            "faces_detected": self.faces_detected,
            "model": self.model,
            "results": [
                {
                    "platform": r.get("platform", "Unknown"),
                    "url": r.get("url", ""),
                    "face_similarity": r.get("face_similarity", 0.0),
                    "classification": r.get("classification", "LOW"),
                }
                for r in self.results
            ],
            "verification_hash": self.record_hash,
            "timestamp": self.timestamp,
            "blockchain": self.blockchain,
            "social_profiles": self.social_profiles,
            "profile_face_checks": self.profile_face_checks,
        }
