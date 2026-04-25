#!/usr/bin/env python3
import sys
import yaml
import jsonschema
import os

def validate_card(card_path, schema_path):
    with open(card_path, 'r') as f:
        card = yaml.safe_load(f)
    with open(schema_path, 'r') as f:
        schema = yaml.safe_load(f)
    
    try:
        jsonschema.validate(instance=card, schema=schema)
        print(f"SUCCESS: {card_path} is valid.")
        return True
    except jsonschema.exceptions.ValidationError as e:
        print(f"ERROR: {card_path} failed validation:")
        print(e.message)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: validate_skill_card.py <path_to_yaml>")
        sys.exit(1)
    
    # Simple default paths for this harness
    SCHEMA = os.path.expanduser("~/.securatron/global/schemas/skill-card.v1.yaml")
    
    success = True
    for path in sys.argv[1:]:
        if not validate_card(path, SCHEMA):
            success = False
    
    if not success:
        sys.exit(1)
