"""
conftest.py — Project-wide pytest configuration for LuminaClause backend.

Registers custom marks so pytest does not emit PytestUnknownMarkWarning.
"""

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a live database "
        "(set TEST_DATABASE_URL to run them).",
    )
