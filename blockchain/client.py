import json
from pathlib import Path

from web3 import Web3
from eth_account import Account

from config import RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS
from utils.hashing import sha256_string


class BlockchainClient:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        self.connected = self.w3.is_connected()

        abi_path = Path(__file__).parent / "abi.json"
        with open(abi_path) as f:
            abi_data = json.load(f)
        self.abi = abi_data["abi"]

        self.contract = None
        if self.connected and CONTRACT_ADDRESS:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(CONTRACT_ADDRESS),
                abi=self.abi,
            )

        self.account = None
        if PRIVATE_KEY:
            self.account = Account.from_key(PRIVATE_KEY)

    def is_ready(self) -> bool:
        return self.connected and self.account is not None and self.contract is not None

    def record_verification(self, record_hash: str, input_hash: str, candidate_hash: str, similarity: float, matched: bool) -> dict:
        if not self.is_ready():
            return {"success": False, "error": "Blockchain client not configured. Set PRIVATE_KEY, CONTRACT_ADDRESS in .env"}

        input_bytes = bytes.fromhex(record_hash)
        input_image_hash = bytes.fromhex(input_hash)
        candidate_bytes = bytes.fromhex(sha256_string(candidate_hash)) if candidate_hash else bytes(32)
        score_int = int(similarity * 10000)

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                nonce = self.w3.eth.get_transaction_count(self.account.address)
                tx = self.contract.functions.recordVerification(
                    input_bytes,
                    input_image_hash,
                    candidate_bytes,
                    score_int,
                    matched,
                ).build_transaction({
                    "from": self.account.address,
                    "nonce": nonce,
                    "gas": 500000,
                    "chainId": self.w3.eth.chain_id,
                    "maxFeePerGas": self._max_fee(attempt),
                    "maxPriorityFeePerGas": self._priority_fee(attempt),
                })

                signed = self.account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90, poll_latency=5)

                return {
                    "success": True,
                    "transaction_hash": receipt.transactionHash.hex(),
                    "block_number": receipt.blockNumber,
                    "gas_used": receipt.gasUsed,
                }
            except Exception as e:
                if attempt >= max_attempts:
                    return {"success": False, "error": str(e)}
                continue
        return {"success": False, "error": "Transaction could not be confirmed"}

    def _max_fee(self, attempt: int) -> int:
        try:
            base = self.w3.eth.get_block("latest")["baseFeePerGas"]
            priority = self._priority_fee(attempt)
            return int(base * 3 + priority)
        except Exception:
            return int(self.w3.eth.gas_price * 1.25 ** attempt)

    def _priority_fee(self, attempt: int) -> int:
        base = 1_000_000_000
        try:
            return int(self.w3.eth.max_priority_fee + base * attempt)
        except Exception:
            return base * attempt

    def get_verification(self, record_hash: str) -> dict | None:
        if not self.contract:
            return None
        try:
            record_bytes = bytes.fromhex(record_hash)
            if not self.contract.functions.exists(record_bytes).call():
                return None
            result = self.contract.functions.getVerification(record_bytes).call()
            return {
                "input_image_hash": result[0].hex(),
                "candidate_hash": result[1].hex(),
                "similarity_score": result[2] / 10000,
                "matched": result[3],
                "timestamp": result[4],
            }
        except Exception:
            return None
