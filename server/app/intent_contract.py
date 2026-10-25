import hashlib
import json
import math

# Standard Intent Groups with default keywords (Thai + English)
STANDARD_INTENT_GROUPS = [
    {
        "group": "Smooth Resolution",
        "color": "#2ECC71",
        "description": "Customer shows understanding, acceptance, or completion",
        "default_keywords": ["ขอบคุณ", "เข้าใจแล้ว", "ได้เลย", "โอเค", "ชัดเจน", "thank you", "understood", "got it", "okay", "clear"]
    },
    {
        "group": "Repetitive / Looping",
        "color": "#F39C12",
        "description": "Customer asks same questions repeatedly",
        "default_keywords": ["อีกครั้ง", "ซ้ำ", "ไม่เข้าใจ", "บอกอีกที", "ยังไง", "again", "repeat", "still confused", "tell me again", "how"]
    },
    {
        "group": "Confused / Unclear Intent",
        "color": "#F1C40F",
        "description": "Customer's messages are vague or unclear",
        "default_keywords": ["งง", "สับสน", "ไม่แน่ใจ", "อาจจะ", "บางที", "confused", "unclear", "not sure", "maybe", "perhaps"]
    },
    {
        "group": "Frustrated / Escalating",
        "color": "#E74C3C",
        "description": "Customer expresses negative emotions or dissatisfaction",
        "default_keywords": ["หงุดหงิด", "รำคาญ", "ช้า", "ไม่พอใจ", "แย่", "frustrated", "annoyed", "slow", "dissatisfied", "terrible"]
    },
    {
        "group": "Critical / Human Required",
        "color": "#8E0E00",
        "description": "High-risk topics or explicit human assistance request",
        "default_keywords": ["คืนเงิน", "ทนาย", "ด่วน", "ร้องเรียน", "พูดกับคน", "refund", "lawyer", "urgent", "complaint", "speak to human"]
    }
]

INTENT_COLORS = {group["group"]: group["color"] for group in STANDARD_INTENT_GROUPS}
DECISION_CRITERIA = {
    "Smooth Resolution": "The customer confirms their problem is solved, understands the answer, or accepts the solution.",
    "Repetitive / Looping": "The customer repeats the same unresolved question or asks for the same explanation again.",
    "Confused / Unclear Intent": "The customer is confused, unsure what to do, or cannot clearly explain their request.",
    "Frustrated / Escalating": "The customer complains about poor service, delays, or expresses anger or dissatisfaction.",
    "Critical / Human Required": "The customer explicitly requests a human agent, a refund, or raises a legal complaint.",
}
DECISION_INSTRUCTIONS = "Classify the latest customer message using the conversation context. Choose the most applicable customer conversation status."
DECISION_MODEL_SHA256 = "2d079ee2f6f066b1f368e8d7c819f55214eaef1d0513b312321901f30ab286fb"
DECISION_PROFILE = hashlib.sha256(json.dumps({
    "model_sha256": DECISION_MODEL_SHA256,
    "criteria": list(DECISION_CRITERIA.items()),
    "instructions": DECISION_INSTRUCTIONS,
    "normalize_prior": True,
}, sort_keys=True).encode()).hexdigest()
DECISION_MAX_CONTEXT_BYTES = 2048
DECISION_RESPONSE_FIELDS = {"schema_version", "profile", "selected_key", "confidence", "probabilities"}


def valid_decision_result(data: object) -> bool:
    def score(value):
        try:
            return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
        except OverflowError:
            return False

    if (not isinstance(data, dict) or set(data) != DECISION_RESPONSE_FIELDS
            or type(data['schema_version']) is not int or data['schema_version'] != 1
            or data['profile'] != DECISION_PROFILE or not score(data['confidence'])
            or not isinstance(data['selected_key'], str) or data['selected_key'] not in INTENT_COLORS):
        return False
    probabilities = data['probabilities']
    if (not isinstance(probabilities, dict) or set(probabilities) != set(INTENT_COLORS)
            or not all(score(value) for value in probabilities.values())
            or not math.isclose(sum(probabilities.values()), 1, rel_tol=0, abs_tol=.001)):
        return False
    ordered = sorted(probabilities.values(), reverse=True)
    return ordered[0] > ordered[1] and probabilities[data['selected_key']] == ordered[0]
