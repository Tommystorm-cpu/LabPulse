import json
import os

# Path to your JSON file
JSON_PATH = '/home/monitorpi/Desktop/phone_numbers.json' # Make sure this is the full path to your phone number .json file!

def load_recipients(path):
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get('recipients', [])
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        print("!! Error: JSON file is invalid. !!")
        return []

def save_recipients(path, recipients):
    with open(path, 'w') as f:
        json.dump({'recipients': recipients}, f, indent=4)
        print("--Changes saved--")

def display_recipients(recipients):
    print("\nCurrent phone numbers:")
    if not recipients:
        print("  (none)")
    else:
        for i, num in enumerate(recipients, 1):
            print(f"  {i}. {num}")

def main():
    recipients = load_recipients(JSON_PATH)

    while True:
        display_recipients(recipients)
        print("\nChoose an option:")
        print("  [1] Add a number")
        print("  [2] Remove a number by index")
        print("  [3] Quit")

        choice = input("Enter your choice (1-3): ").strip()

        if choice == '1':
            new_number = input("Enter the phone number to add (e.g. +447700900000): ").strip()
            if new_number in recipients:
                print("!! That number is already in the list !!")
            else:
                recipients.append(new_number)
                save_recipients(JSON_PATH, recipients)

        elif choice == '2':
            if not recipients:
                print("!! The list is empty, nothing to remove !!")
                continue

            try:
                index = int(input("Enter the number's index to remove: ").strip())
                if 1 <= index <= len(recipients):
                    removed = recipients.pop(index - 1)
                    print(f"-- Removed {removed} --")
                    save_recipients(JSON_PATH, recipients)
                else:
                    print("XX Invalid index XX")
            except ValueError:
                print("XX Please enter a valid number XX")

        elif choice == '3':
            print("--Exiting--")
            break

        else:
            print("XX Invalid choice. Please enter 1, 2, or 3 XX")

if __name__ == '__main__':
    main()
