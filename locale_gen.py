import os
import re
import xml.etree.ElementTree as ET
import shutil
import sys

COMMON_WORDS = {
    'the', 'your', 'to', 'for', 'and', 'with', 'a', 'of', 'on', 'in', 'is', 'package'
}
key_index = [1]


def ensure_in_app_module():
    cwd = os.getcwd()
    expected = os.path.join(cwd, "src", "main", "res")
    gradle_file = os.path.join(cwd, "build.gradle")

    if not os.path.isdir(expected):
        print("❌ Error: 'src/main/res/' not found in current directory.")
        print("   Please run this script inside your Android app module (e.g., app/ or app-mob/)")
        sys.exit(1)

    if not os.path.isfile(gradle_file):
        print("⚠️ Warning: No 'build.gradle' found. Are you sure this is an Android app module?")


def find_res_folder():
    return os.path.join(os.getcwd(), "src", "main", "res")


def generate_short_key(text, existing_keys):
    words = re.split(r'\W+', text.lower())
    filtered = [w for w in words if w and w not in COMMON_WORDS]
    base_words = filtered[:3]
    base = "_".join(base_words)

    if not base or base[0].isdigit():
        base = f"key_{key_index[0]}"
        key_index[0] += 1

    if base[0].isdigit():
        base = "k_" + base

    key = base.lower()

    count = 1
    while key in existing_keys:
        key = f"{base}_{count}".lower()
        count += 1

    return key


def escape_android_string(s):
    return (s.replace("&", "&amp;")
              .replace("'", "\\'")
              .replace('"', "&quot;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace("\n", "\\n"))


def load_or_create_strings_xml(folder):
    path = os.path.join(folder, "strings.xml")
    if os.path.exists(path):
        tree = ET.parse(path)
        root = tree.getroot()
    else:
        root = ET.Element("resources")
        tree = ET.ElementTree(root)
    return tree, root, path


def sync_other_languages(res_dir, default_keys, default_values, dry_run):
    for folder in os.listdir(res_dir):
        if folder.startswith("values-"):
            lang_folder = os.path.join(res_dir, folder)
            lang_tree, lang_root, lang_path = load_or_create_strings_xml(lang_folder)

            added_count = 0
            for key, value in zip(default_keys, default_values):
                if lang_root.find(f"./string[@name='{key}']") is None:
                    if not dry_run:
                        string_elem = ET.SubElement(lang_root, "string", name=key)
                        string_elem.text = escape_android_string(f"TODO: Translate {value}")
                    added_count += 1

            if added_count > 0:
                if not dry_run:
                    lang_tree.write(lang_path, encoding="utf-8", xml_declaration=True)
                print(f"✔ Synced {added_count} missing strings to {lang_path}")


def main():
    dry_run = "--dry-run" in sys.argv

    ensure_in_app_module()

    res_dir = find_res_folder()
    values_dir = os.path.join(res_dir, "values")
    strings_xml_path = os.path.join(values_dir, "strings.xml")

    if not os.path.exists(strings_xml_path):
        raise Exception(f"❌ Could not find strings.xml at {strings_xml_path}")

    # Load default strings
    tree = ET.parse(strings_xml_path)
    root = tree.getroot()

    existing_keys = {}
    value_to_key = {}

    for string in root.findall('string'):
        key = string.get('name')
        val = string.text or ""
        existing_keys[key] = val
        value_to_key[val] = key

    new_strings = {}
    files_to_update = []

    # Find layout folders
    layout_dirs = [os.path.join(res_dir, d) for d in os.listdir(res_dir)
                   if d.startswith("layout") and os.path.isdir(os.path.join(res_dir, d))]

    print("✔ Detected layout folders:")
    for d in layout_dirs:
        print(" -", d)

    print("✔ Detected strings.xml:", strings_xml_path)

    for layout_dir in layout_dirs:
        for file in os.listdir(layout_dir):
            if not file.endswith(".xml"):
                continue

            file_path = os.path.join(layout_dir, file)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            modified = content

            # Detect missing @string/ references
            missing_keys = re.findall(r'@string/([a-zA-Z0-9_]+)', content)
            for ref_key in missing_keys:
                if ref_key not in existing_keys and ref_key not in new_strings:
                    new_strings[ref_key] = f"MISSING: {ref_key}"

            # Replace android:text, android:hint, android:contentDescription
            matches = re.findall(r'(\b(?:android:)?(?:text|hint|contentDescription))="([^"]+)"', content)
            for attr, value in matches:
                if value.startswith("@") or value.strip() == "" or value == "---":
                    continue

                if value in value_to_key:
                    key = value_to_key[value]
                else:
                    key = generate_short_key(value, {**existing_keys, **new_strings})
                    new_strings[key] = value
                    value_to_key[value] = key

                new_attr = f'{attr}="@string/{key}"'
                pattern = re.escape(f'{attr}="{value}"')
                modified = re.sub(pattern, new_attr, modified, count=1)

            if content != modified:
                files_to_update.append(file_path)

                if not dry_run:
                    backup = file_path + ".bak"
                    shutil.copyfile(file_path, backup)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(modified)
                    print(f"✔ Updated {file} (backup: {file}.bak)")

    # Report changes
    if dry_run:
        if files_to_update:
            print("\n⚙️ Dry Run: Files that would be updated:")
            for f in files_to_update:
                print(" -", f)
        else:
            print("\n✅ Dry Run: No layout files need updates.")

    # Add new strings to default
    if new_strings:
        if dry_run:
            print(f"\n⚙️ Dry Run: {len(new_strings)} new strings would be added to default and translation files.")
        else:
            for key, value in new_strings.items():
                if root.find(f"./string[@name='{key}']") is None:
                    string_elem = ET.SubElement(root, "string", name=key)
                    string_elem.text = escape_android_string(value)
            tree.write(strings_xml_path, encoding="utf-8", xml_declaration=True)
            print(f"✔ Added {len(new_strings)} new strings to {strings_xml_path}")

    # Always sync translations
    default_keys = list(existing_keys.keys()) + list(new_strings.keys())
    default_values = list(existing_keys.values()) + list(new_strings.values())

    sync_other_languages(res_dir, default_keys, default_values, dry_run)

    if not new_strings and dry_run:
        print("\n⚙️ Dry Run: No new keys, but translation folders would be synced.")


if __name__ == "__main__":
    main()
