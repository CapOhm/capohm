# memory.py

import json
import os
import time

MEMORY_FILE = "borg_memory.json"
MEMORY_LIMIT = 10

# Load memory
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

# Save memory
def save_memory(long_term_memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(long_term_memory, f)

# Add a fact to memory
def remember_fact(long_term_memory, fact):
    if len(long_term_memory) >= MEMORY_LIMIT:
        return False
    long_term_memory[time.time()] = fact
    save_memory(long_term_memory)
    return True

# List memories
def list_memories(long_term_memory):
    keys = list(long_term_memory.keys())
    for idx, k in enumerate(keys):
        print(f"{idx + 1}: {long_term_memory[k]}")

# Delete a memory
def delete_memory(long_term_memory, index):
    keys = list(long_term_memory.keys())
    if 0 <= index < len(keys):
        deleted = long_term_memory.pop(keys[index])
        save_memory(long_term_memory)
        return deleted
    return None
