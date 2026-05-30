# New Capohm Inventory Module

import json
import os
import subprocess

PRODUCTS_FILE = "products.json"

# Load products
if os.path.exists(PRODUCTS_FILE):
    with open(PRODUCTS_FILE, "r") as f:
        products = json.load(f)
else:
    products = {}

# Save products
def save_products():
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=4)

# Lower stock by 1 for a given product name
def take_product(spoken_name):
    matched = None
    for product_id, details in products.items():
        if spoken_name.lower() in details["name"].lower():
            matched = (product_id, details)
            break

    if matched:
        product_id, details = matched
        if details["in_stock"] > 0:
            details["in_stock"] -= 1
            save_products()
            print(f"✅ Recorded. {details['in_stock']} {details['name']} remaining.")
        else:
            print(f"⚠️ No {details['name']} left in stock!")
    else:
        print(f"❓ Could not find product matching '{spoken_name}'.")

# List low stock items
def list_low_stock():
    low_items = []
    for product_id, details in products.items():
        if details["in_stock"] <= details["threshold"]:
            low_items.append(details["name"])

    if low_items:
        print("📦 Low stock detected:")
        for item in low_items:
            print(f"- {item}")
    else:
        print("✅ All stock levels are sufficient.")

# Confirm and order low stock items
def get_low_stock_items():
    low_items = []
    for product_id, details in products.items():
        if details["in_stock"] <= details["threshold"]:
            low_items.append(details["name"])
    return low_items

def order_low_stock(items):
    if items:
        print("🛒 Ordering low stock items:")
        for name in items:
            print(f"- Ordering {name}")
            try:
                subprocess.run(["python3", "ordering.py", name], check=True)
            except Exception as e:
                print(f"⚠️ Failed to order {name}: {e}")
        print("✅ Order process completed.")
    else:
        print("✅ No items need ordering.")


# Example usage:
if __name__ == "__main__":
    while True:
        command = input("Speak: ").strip()
        if command.lower() in ["exit", "quit"]:
            break
        if command.lower().startswith("taking"):
            taking_item = command[len("taking"):].strip()
            take_product(taking_item)
        elif command.lower() == "what is low":
            list_low_stock()
        elif command.lower() == "order what is low":
            order_low_stock()
