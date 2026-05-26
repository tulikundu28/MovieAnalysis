import os
import pytest

# Provide a JWT secret so jwt_handler works without a .env file
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
