"""Salesforce's Track-B vocabulary — OBJECTS: {object: {"table", "fields"
(api_name -> type), "assignable_fields", "taggable_fields"}} — DERIVED from
app_catalog.py, the one shared per-app object/field catalog Track A's
FIELD_CATALOG also reads. This module is now a thin, Salesforce-scoped
compat view kept so automation/planner.py, automation/plan_validator.py,
and salesforce_mock.py don't need to know they're really reading a
multi-app catalog underneath — see app_catalog.py's own docstring for why
that catalog exists and how a second app onboards into it.
"""
import app_catalog

OBJECTS = app_catalog.api_objects("salesforce")
