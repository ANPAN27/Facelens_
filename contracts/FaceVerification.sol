// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract FaceVerification {
    struct Verification {
        bytes32 inputImageHash;
        bytes32 candidateHash;
        uint256 similarityScore;
        bool matched;
        uint256 timestamp;
    }

    mapping(bytes32 => Verification) public verifications;

    event VerificationRecorded(bytes32 indexed recordHash, uint256 timestamp);

    function recordVerification(
        bytes32 recordHash,
        bytes32 inputImageHash,
        bytes32 candidateHash,
        uint256 similarityScore,
        bool matched
    ) external returns (bytes32) {
        require(verifications[recordHash].timestamp == 0, "Record already exists");

        verifications[recordHash] = Verification({
            inputImageHash: inputImageHash,
            candidateHash: candidateHash,
            similarityScore: similarityScore,
            matched: matched,
            timestamp: block.timestamp
        });

        emit VerificationRecorded(recordHash, block.timestamp);

        return recordHash;
    }

    function getVerification(bytes32 recordHash)
        external
        view
        returns (
            bytes32 inputImageHash,
            bytes32 candidateHash,
            uint256 similarityScore,
            bool matched,
            uint256 timestamp
        )
    {
        Verification storage v = verifications[recordHash];
        return (
            v.inputImageHash,
            v.candidateHash,
            v.similarityScore,
            v.matched,
            v.timestamp
        );
    }

    function exists(bytes32 recordHash) external view returns (bool) {
        return verifications[recordHash].timestamp != 0;
    }
}