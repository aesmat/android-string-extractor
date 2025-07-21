import os
import re
import argparse
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

COMMON_WORDS = {
    'the', 'your', 'to', 'for', 'and', 'with', 'a', 'of', 'on', 'in', 'is', 'package'
}

SKIP_VALUES = {"", "---", "..."}

COMMON_ATTRS = ['android:text', 'android:hint', 'android:contentDescription']

def generate_short_key(text, existing_keys, common_words, key_index):
    words = re.findall(r'\w+', text.lower())
    filtered = [w for w in words if w not in common_words]
    base = '_'.join(filtered[:3])
    if not base or base[0].isdigit():
        base = f'key_{key_index[0]}'
        key_index[0] += 1
    key = base
    count = 1
    while key in existing_keys:
        key = f'{base}_{count}'
        count += 1
    return key

def find_strings_xml(base_dir):
    for root, dirs, files in os.walk(base_dir):
        if "src/main/res/values" in root.replace("\\", "/") and "strings.xml" in files:
            return os.path.join(root, "strings.xml")
    return None

def load_strings_xml(strings_path):
    tree = ET.parse(strings_path)
    root = tree.getroot()
    existing = {}
    for string in root.findall('string'):
        existing[string.attrib['name']] = string.text
    return existing, root

def extract_xml_strings(res_dir, existing_values, key_index, dry_run=False):
    new_strings = {}

    for root_dir, _, files in os.walk(res_dir):
        if 'layout' not in root_dir:
            continue

        for file in files:
            if file.endswith(".xml"):
                path = os.path.join(root_dir, file)
                try:
                    tree = ET.parse(path)
                    root = tree.getroot()
                    modified = False

                    for elem in root.iter():
                        for attr in COMMON_ATTRS:
                            value = elem.get(attr)
                            if value and not value.startswith("@") and value.strip() not in SKIP_VALUES:
                                # Check if value exists in strings.xml
                                existing_key = next((k for k, v in existing_values.items() if v == value), None)
                                if existing_key:
                                    # Use existing key
                                    elem.set(attr, f"@string/{existing_key}")
                                    modified = True
                                    print(f"✔ Reused existing key '{existing_key}' for value '{value}' in {file}")
                                else:
                                    # Generate new key as before
                                    key = generate_short_key(value, existing_values, COMMON_WORDS, key_index)
                                    new_strings[key] = value
                                    existing_values[key] = value
                                    elem.set(attr, f"@string/{key}")
                                    modified = True

                    if not dry_run and modified:
                        backup_path = f"{path}.bak"
                        with open(backup_path, 'w', encoding='utf-8') as backup_file:
                            backup_file.write(ET.tostring(root, encoding='unicode'))
                        tree.write(path, encoding='utf-8', xml_declaration=True)
                        print(f"✔ Updated {file} (backup: {backup_path})")

                except ET.ParseError as e:
                    print(f"⚠ Failed to parse {file}: {e}")
                    continue

    return new_strings


def extract_java_strings(java_dir, existing_values, key_index, dry_run=False):
    new_strings = {}
    pattern = re.compile(r'(\.setText\s*\(\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"\s*\)', re.DOTALL)

    for root, _, files in os.walk(java_dir):
        for file in files:
            if file.endswith(".java"):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

                modified = content
                matches = pattern.findall(content)

                for prefix, raw_string in matches:
                    string = raw_string.strip()
                    if (not string or string.isnumeric() or string.startswith("@") or string.strip() in SKIP_VALUES):
                        continue
                    existing_key = next((k for k, v in existing_values.items() if v == string), None)
                    if existing_key:
                        replacement = f'{prefix}getString(R.string.{existing_key}))'
                        original = f'{prefix}"{raw_string}")'
                        modified = modified.replace(original, replacement)
                        print(f"✔ Reused existing key '{existing_key}' for value '{string}' in {file}")
                    else:
                        key = generate_short_key(string, existing_values, COMMON_WORDS, key_index)
                        new_strings[key] = string
                        existing_values[key] = string
                        replacement = f'{prefix}getString(R.string.{key}))'
                        original = f'{prefix}"{raw_string}")'
                        modified = modified.replace(original, replacement)

                if not dry_run and content != modified:
                    backup_path = path + ".bak"
                    with open(backup_path, 'w', encoding='utf-8') as backup_file:
                        backup_file.write(content)

                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(modified)

                    print(f"✔ Updated {file} (backup: {file}.bak)")

    return new_strings

def write_strings_xml(strings_path, root, new_strings, dry_run):
    for key, value in new_strings.items():
        elem = ET.Element('string', name=key)
        elem.text = escape(value)
        root.append(elem)

    if not dry_run:
        tree = ET.ElementTree(root)
        ET.indent(tree, space="    ", level=0)
        tree.write(strings_path, encoding="utf-8", xml_declaration=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--java', action='store_true', help='Extract strings from Java')
    parser.add_argument('--xml', action='store_true', help='Extract strings from XML layouts')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without writing files')
    args = parser.parse_args()

    if not (args.xml or args.java):
        print("⚠ Please specify at least one of --xml or --java to extract strings.")
        parser.print_help()
        return

    project_dir = os.getcwd()
    strings_path = find_strings_xml(project_dir)
    if not strings_path:
        print(f"❌ Could not find strings.xml in {project_dir}")
        return
    
    try:
        existing_keys, root = load_strings_xml(strings_path)
    except FileNotFoundError:
        print(f"❌ Could not load strings.xml at {strings_path}")
        return

    key_index = [1]
    new_strings = {}

    # Extract from XML layout
    if args.xml:
        res_dir = os.path.join(os.path.dirname(strings_path), "..", "..", "res")
        if os.path.exists(res_dir):
            xml_strings = extract_xml_strings(res_dir, existing_keys, key_index, args.dry_run)
            new_strings.update(xml_strings)
        else:
            print(f"❌ Could not find {res_dir}")

    # Extract from Java .setText()
    if args.java:
        java_dir = os.path.join(project_dir, 'src', 'main', 'java')
        if os.path.exists(java_dir):
            java_strings = extract_java_strings(java_dir, existing_keys, key_index, args.dry_run)
            new_strings.update(java_strings)
        else:
            print(f"❌ Could not find {java_dir}")

    if new_strings:
        print(f"✔ Found {len(new_strings)} new strings.")
        write_strings_xml(strings_path, root, new_strings, args.dry_run)
        if args.dry_run:
            for k, v in new_strings.items():
                print(f"[DRY RUN] {k}: {v}")
        else:
            print(f"✔ Updated {strings_path}")
    else:
        print("⚠ No new strings found.")

if __name__ == "__main__":
    main()
