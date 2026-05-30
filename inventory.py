import json
import os

INVENTORY_FILE = "inventory.json"

def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        with open(INVENTORY_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

def save_inventory(data):
    with open(INVENTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def take_item(item_name, amount=1):
    inventory = load_inventory()
    if item_name in inventory:
        inventory[item_name]["quantity"] -= amount
        if inventory[item_name]["quantity"] < 0:
            inventory[item_name]["quantity"] = 0
        save_inventory(inventory)
        return f"Took {amount} {item_name}(s). Remaining: {inventory[item_name]['quantity']}"
    else:
        return f"{item_name} not found in inventory."

def restock_item(item_name, amount, part_number=None):
    inventory = load_inventory()
    if item_name not in inventory:
        inventory[item_name] = {"quantity": 0, "part_number": part_number or "unknown"}
    inventory[item_name]["quantity"] += amount
    if part_number:
        inventory[item_name]["part_number"] = part_number
    save_inventory(inventory)
    return f"Restocked {item_name} by {amount}. Total now: {inventory[item_name]['quantity']}"

def list_inventory():
    inventory = load_inventory()
    if not inventory:
        return "Inventory is empty."
    lines = []
    for item, info in inventory.items():
        lines.append(f"{item}: {info['quantity']} (Part: {info['part_number']})")
    return "\n".join(lines)
