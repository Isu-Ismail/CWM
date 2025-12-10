
"""
Unified JSON Validator System for CWM
"""


def default_for_type(t):
    if t is int:
        return 0
    if t is float:
        return 0.0
    if t is str:
        return ""
    if t is bool:
        return False
    if t is list:
        return []
    if t is dict:
        return {}
    if isinstance(t, tuple):
        return None
    return None


def _validate_value(value, expected):
    """Validate a primitive value."""
    if isinstance(expected, tuple):
        if not isinstance(value, expected):
            return default_for_type(expected)
        return value

    if not isinstance(value, expected):
        return default_for_type(expected)
    return value


def _validate_list(data, subschema, partial=False):
    """Validate a list. Passes partial flag down to items."""
    if not isinstance(data, list):
        return []

    if not subschema:
        return data

    item_schema = subschema[0]
    validated = []
    for item in data:
        validated.append(validate(item, item_schema, partial=partial))
    return validated


def _validate_dict(data, schema, partial=False):
    """
    Validate a dictionary.

    modes:
    - partial=False (Strict): Result starts empty. Only Schema keys are added. Missing keys generated.
    - partial=True (Loose): Result starts as copy of Data. Unknown keys preserved. Missing keys ignored.
    """
    if not isinstance(data, dict):
        return {}

    if partial:
        result = data.copy()
    else:
        result = {}

    for key, subschema in schema.items():
        if key in data:
            result[key] = validate(data[key], subschema, partial=partial)
        elif not partial:
            result[key] = generate_default(subschema)

    return result


def generate_default(schema):
    """Generate a default value for complex schema."""
    if isinstance(schema, dict):
        return {k: generate_default(v) for k, v in schema.items()}
    if isinstance(schema, list):
        return []
    return default_for_type(schema)


def validate(data, schema, partial=False):
    """
    Main entry point.
    partial=True: Checks only fields present in 'data'. Does not add missing or remove extra.
    """
    if isinstance(schema, dict):
        return _validate_dict(data, schema, partial=partial)

    if isinstance(schema, list):
        return _validate_list(data, schema, partial=partial)

    return _validate_value(data, schema)


def validate_service_entry(entry):
    template = {
        "project_id": int,
        "alias": str,
        "pid": (int, type(None)),
        "viewers": [int],
        "status": str,
        "start_time": (int, float),
        "log_path": str,
        "cmd": str
    }
    return validate(entry, template)


SCHEMAS = {
    "projects.json": {
        "last_id": int,
        "last_group_id": int,
        "projects": [
            {
                "id": int,
                "alias": str,
                "path": str,
                "hits": int,
                "startup_cmd": (str, list, type(None)),
                "group": (int, type(None)),
            }
        ],
        "groups": [
            {
                "id": int,
                "alias": str,
                "project_list": [
                    {
                        "id": int,
                        "verify": str
                    }
                ]
            }
        ],
    },

    "saved_cmds.json": {
        "last_saved_id": int,
        "commands": [
            {
                "id": int,
                "type": str,
                "var": str,
                "cmd": str,
                "tags": [str],
                "fav": (bool, type(None)),
                "created_at": str,
                "updated_at": str
            }
        ]
    },

    "fav_cmds.json": [int],

    "history.json": {
        "last_sync_id": int,
        "commands": [
            {
                "id": int,
                "cmd": str,
                "timestamp": str
            }
        ]
    },

    "watch_session.json": {
        "isWatching": None or bool,
        "shell": None or str,
        "hook_file": None or str,
        "started_at": None or (str, int),  # Fixed syntax from 'str or int'
    },

    "config.json": {
        "history_file": (str, type(None)),
        "project_markers": [str],
        "default_editor": str,
        "default_terminal": (str, type(None)),
        "code_theme": str,

        "gemini": {
            "model": (str, type(None)),
            "key": (str, type(None))
        },
        "openai": {
            "model": (str, type(None)),
            "key": (str, type(None))
        },
        "local_ai": {
            "model": (str, type(None))
        },

        "ai_instruction": str
    },

    "services.json": dict,
}


