

"""project_type là khái niệm nghiệp vụ cấp project: 'review' | 'reup'.
Module này là DOMAIN layer — không phụ thuộc persistence/UI. Xem ADR-010.

Từ vựng 'reup' khớp TOOL_MODES hiện hữu trong main_qt (review/reup) — sửa domain
modeling sau Step 1 (trước đây gọi nhầm 'dubbing'), tránh nợ mapping cho Batch C.
"""
import logging
log = logging.getLogger(__name__)
PROJECT_TYPE_REVIEW = 'review'
PROJECT_TYPE_REUP = 'reup'
VALID_PROJECT_TYPES = frozenset({PROJECT_TYPE_REVIEW, PROJECT_TYPE_REUP})
DEFAULT_PROJECT_TYPE = PROJECT_TYPE_REVIEW
def normalize_project_type(value):
    if isinstance(value, str):
        v = value.strip().lower()
        if v in VALID_PROJECT_TYPES:
            return v
    return DEFAULT_PROJECT_TYPE
def validate_project_type_strict(value):
    if isinstance(value, str):
        v = value.strip().lower()
        if v in VALID_PROJECT_TYPES:
            return v
    raise ValueError(f'''project_type không hợp lệ: {value!r}. Phải là một trong {sorted(VALID_PROJECT_TYPES)}.''')
def get_project_type(session_data):
    if not session_data:
        return DEFAULT_PROJECT_TYPE
    return normalize_project_type(session_data.get('project_type'))
def is_review_project(session_data):
    return get_project_type(session_data) == PROJECT_TYPE_REVIEW
def is_reup_project(session_data):
    return get_project_type(session_data) == PROJECT_TYPE_REUP