# src/cwm/schema_validator.py
import copy

"""
Unified JSON Validator System for CWM
-------------------------------------
This module provides:
• SCHEMAS: Structure for every known JSON file
• validate(): Main entry point
• Auto-healing for type errors, missing keys, corrupted structures
• Default value generation
"""

# -------------------------------------
# Default Value Helpers
# -------------------------------------

def default_for_type(t):
    """Return safe default for expected type."""
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
    if isinstance(t, tuple):  # e.g. (str, type(None))
        return None
    return None


# -------------------------------------
# Core Validators
# -------------------------------------

def _validate_value(value, expected):
    """Validate a primitive value."""
    if isinstance(expected, tuple):  # e.g. (str, type(None))
        if not isinstance(value, expected):
            return default_for_type(expected)
        return value

    if not isinstance(value, expected):
        return default_for_type(expected)
    return value


def _validate_list(data, subschema):
    """
    Validate a list and all its items.
    subschema is the first item in the definition list, e.g. [int] -> int
    """
    if not isinstance(data, list):
        return []

    # If the schema is just [], we accept any list content (generic list)
    if not subschema:
        return data

    item_schema = subschema[0]
    validated = []
    for item in data:
        # Recursively validate each item against the item_schema
        validated.append(validate(item, item_schema))
    return validated


def _validate_dict(data, schema):
    """Validate a dictionary using schema keys."""
    if not isinstance(data, dict):
        data = {}

    result = {}

    for key, subschema in schema.items():
        if key not in data:
            # missing → generate default recursively
            result[key] = generate_default(subschema)
        else:
            result[key] = validate(data[key], subschema)

    # Preserve extra keys? 
    # Current logic: No. Only keys defined in schema are kept (Strict).
    return result


def generate_default(schema):
    """Generate a default value for complex schema."""
    if isinstance(schema, dict):
        return {k: generate_default(v) for k, v in schema.items()}
    if isinstance(schema, list):
        return []
    return default_for_type(schema)


def validate(data, schema):
    """Main entry point — validates any value against schema."""
    if isinstance(schema, dict):
        return _validate_dict(data, schema)

    if isinstance(schema, list):
        # Pass the whole list schema so _validate_list can extract the item type
        return _validate_list(data, schema)

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


# -------------------------------------
# MASTER SCHEMA REGISTRY
# -------------------------------------

SCHEMAS = {

    # -----------------------------
    # projects.json
    # -----------------------------
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
                # STRICT VALIDATION for new structure
                "project_list": [
                    {
                        "id": int,
                        "verify": str
                    }
                ]
            }
        ],
    },

    # -----------------------------
    # saved_cmds.json
    # -----------------------------
    "saved_cmds.json": {
        "last_saved_id": int,
        "commands": [
            {
                "id": int,
                "type": str,
                "var": str,
                "cmd": str,
                "tags": [str], # Assuming list of strings
                "fav": (bool, type(None)), # Handle null or bool
                "created_at": str,
                "updated_at": str
            }
        ]
    },

    # -----------------------------
    # fav_cmds.json
    # -----------------------------
    "fav_cmds.json": [int],

    # -----------------------------
    # history.json
    # -----------------------------
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

    # -----------------------------
    # watch_session.json
    # -----------------------------
    "watch_session.json": {
        "isWatching": bool,
        "marker": str,
        "timestamp": str,
    },

    # -----------------------------
    # config.json
    # -----------------------------
    "config.json": {
        "history_file": (str, type(None)),
        "project_markers": [str],
        "default_editor": str,
        "default_terminal": (str, type(None)),
        "suppress_history_warning": bool,
        "code_theme": str,

        # nested AI sections
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
    
    # -----------------------------
    # services.json
    # -----------------------------
    "services.json": dict, 
}