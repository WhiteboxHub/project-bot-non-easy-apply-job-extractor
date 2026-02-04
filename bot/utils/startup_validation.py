"""
Startup validation for required secrets and configuration.
Ensures all critical environment variables are present before execution.
"""

import os
import sys
from typing import List, Tuple
from dotenv import load_dotenv

load_dotenv()


class ValidationError(Exception):
    """Raised when startup validation fails"""
    pass


def validate_secrets() -> Tuple[bool, List[str]]:
    """
    Validate all required secrets are present.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Required secrets
    required_secrets = {
        "SECRET_KEY": "API secret key for authentication",
        "WBL_API_URL": "Base URL for the API",
    }
    
    # Optional but recommended
    recommended_secrets = {
        "API_TOKEN": "API authentication token (or provide API_EMAIL/API_PASSWORD)",
    }
    
    # Check required secrets
    for key, description in required_secrets.items():
        value = os.getenv(key, "").strip()
        if not value:
            errors.append(f"❌ MISSING REQUIRED: {key} ({description})")
    
    # Check recommended secrets with warnings
    for key, description in recommended_secrets.items():
        value = os.getenv(key, "").strip()
        if not value:
            # Check if alternative auth is provided
            email = os.getenv("API_EMAIL", "").strip()
            password = os.getenv("API_PASSWORD", "").strip()
            if not (email and password):
                errors.append(f"⚠️  MISSING RECOMMENDED: {key} ({description})")
    
    # Validate candidate configuration
    if not os.path.exists("candidate.yaml"):
        errors.append("❌ MISSING: candidate.yaml file not found")
    
    return len(errors) == 0, errors


def validate_configuration() -> Tuple[bool, List[str]]:
    """
    Validate configuration values are sensible.
    
    Returns:
        Tuple of (is_valid, list_of_warnings)
    """
    warnings = []
    
    # Check numeric configurations
    try:
        distance = int(os.getenv("DISTANCE_MILES", "50"))
        if distance < 1 or distance > 100:
            warnings.append(f"⚠️  DISTANCE_MILES={distance} is unusual (expected 1-100)")
    except ValueError:
        warnings.append("⚠️  DISTANCE_MILES is not a valid number")
    
    try:
        max_apps = int(os.getenv("MAX_APPLICATIONS_PER_RUN", "50"))
        if max_apps < 1 or max_apps > 1000:
            warnings.append(f"⚠️  MAX_APPLICATIONS_PER_RUN={max_apps} is unusual (expected 1-1000)")
    except ValueError:
        warnings.append("⚠️  MAX_APPLICATIONS_PER_RUN is not a valid number")
    
    # Check dry run mode
    dry_run = os.getenv("DRY_RUN", "false").lower()
    if dry_run == "true":
        warnings.append("ℹ️  DRY_RUN mode is ENABLED - no data will be saved")
    
    return True, warnings


def run_startup_validation(strict: bool = True) -> bool:
    """
    Run all startup validations.
    
    Args:
        strict: If True, exit on validation failure. If False, just warn.
    
    Returns:
        True if all validations passed, False otherwise
    """
    # Check if validation is enabled
    if os.getenv("VALIDATE_SECRETS_AT_STARTUP", "true").lower() != "true":
        print("ℹ️  Startup validation is disabled (VALIDATE_SECRETS_AT_STARTUP=false)")
        return True
    
    print("=" * 60)
    print("🔍 Running Startup Validation...")
    print("=" * 60)
    
    all_valid = True
    
    # Validate secrets
    secrets_valid, secret_errors = validate_secrets()
    if not secrets_valid:
        all_valid = False
        print("\n❌ SECRET VALIDATION FAILED:\n")
        for error in secret_errors:
            print(f"  {error}")
    else:
        print("\n✅ All required secrets are present")
    
    # Validate configuration
    config_valid, config_warnings = validate_configuration()
    if config_warnings:
        print("\n⚠️  CONFIGURATION WARNINGS:\n")
        for warning in config_warnings:
            print(f"  {warning}")
    else:
        print("✅ Configuration looks good")
    
    print("\n" + "=" * 60)
    
    if not all_valid and strict:
        print("❌ Startup validation failed. Please fix the errors above.")
        print("=" * 60)
        sys.exit(1)
    
    if all_valid:
        print("✅ Startup validation passed!")
    
    print("=" * 60 + "\n")
    
    return all_valid


if __name__ == "__main__":
    # Run validation when executed directly
    run_startup_validation(strict=True)
