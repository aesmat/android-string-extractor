import os
import re
import argparse
import xml.etree.ElementTree as ET

# Register namespaces so ET writes back the original prefixes
# instead of auto-generating ns0, ns1, …
ET.register_namespace('android', 'http://schemas.android.com/apk/res/android')
ET.register_namespace('app',     'http://schemas.android.com/apk/res-auto')
ET.register_namespace('tools',   'http://schemas.android.com/tools')

COMMON_WORDS = {
    'the', 'your', 'to', 'for', 'and', 'with', 'a', 'of', 'on', 'in', 'is', 'package'
}

SKIP_VALUES = {"", "---", "..."}

# FIX 1: require at least one digit so "---" / "..." / "+-" are NOT flagged as numeric.
# Lookahead (?=.*\d) ensures a digit must be present somewhere in the value.
_NUMERIC_RE = re.compile(r'^(?=.*\d)[\d\s.,\'$€£¥%+\-]+$')

# XML attributes to scan (both prefixed and namespace-expanded forms for robustness)
COMMON_ATTRS = [
    'android:text', 'android:hint', 'android:contentDescription',
    'android:title', 'android:summary', 'android:message', 'android:label',
    '{http://schemas.android.com/apk/res/android}text',
    '{http://schemas.android.com/apk/res/android}hint',
    '{http://schemas.android.com/apk/res/android}contentDescription',
    '{http://schemas.android.com/apk/res/android}title',
    '{http://schemas.android.com/apk/res/android}summary',
    '{http://schemas.android.com/apk/res/android}message',
    '{http://schemas.android.com/apk/res/android}label',
]

# Comment-skipping via a leading non-capturing alternative.
# When a comment matches, all capture groups are None → replacer leaves it unchanged.
_COMMENT = r'(?://[^\n]*|/\*.*?\*/)'

# Method-call pattern sources — 3 capture groups: (prefix, string, closing)
_METHOD_SOURCES = [
    r'(\.setText\s*\(\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"(\s*\))',
    r'(\.setTitle\s*\(\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"(\s*\))',
    r'(\.setHint\s*\(\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"(\s*\))',
    r'(\.setMessage\s*\(\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"(\s*\))',
    r'(\.setSubtitle\s*\(\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"(\s*\))',
]

# Kotlin property-assignment sources — 2 capture groups: (prefix, string)
_KOTLIN_PROP_SOURCES = [
    r'(\.text\s*=\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"',
    r'(\.title\s*=\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"',
    r'(\.hint\s*=\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"',
    r'(\.message\s*=\s*)"((?:[^"\\]*(?:\\.[^"\\]*)*))"',
]

# Combined patterns: comment alternative first, target second.
# re.sub with a callback replaces all occurrences in one pass.
METHOD_CALL_PATTERNS = [
    re.compile(f'{_COMMENT}|{src}', re.DOTALL) for src in _METHOD_SOURCES
]
KOTLIN_PROP_PATTERNS = [
    re.compile(f'{_COMMENT}|{src}', re.DOTALL) for src in _KOTLIN_PROP_SOURCES
]

# Escaping rules for Android strings.xml text content:
#   &        → &amp;   (required: & starts XML entities)
#   <        → &lt;    (required: < starts XML tags)
#   >        → &gt;    (recommended)
#   '        → &apos;  (XML entity — safe with AAPT1 and AAPT2;
#                       backslash form \' can trigger AAPT2's strict
#                       unicode-escape-sequence validator)
#   "        → no escaping needed in element text (only in attributes)
_XML_ESCAPES = str.maketrans({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": "\\\'"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_numeric_like(s):
    return bool(_NUMERIC_RE.match(s))


def generate_short_key(text, existing_keys, key_index):
    words = re.findall(r'\w+', text.lower())
    filtered = [w for w in words if w not in COMMON_WORDS]
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
    """
    Walk base_dir and return the path to strings.xml.
    FIX 4: dirs are sorted for deterministic traversal; a path containing /app/ is preferred
    over other modules (core/, feature/, etc.) in multi-module projects.
    """
    results = []
    for root, dirs, files in os.walk(base_dir):
        dirs.sort()   # deterministic order across filesystems
        if "src/main/res/values" in root.replace("\\", "/") and "strings.xml" in files:
            results.append(os.path.join(root, "strings.xml"))
    if not results:
        return None
    # Prefer the app module
    for r in results:
        if '/app/' in r.replace('\\', '/'):
            return r
    return results[0]


def load_strings_xml(strings_path):
    """
    Return (existing_values dict, non_translatable_keys set).
    FIX 3: root element no longer returned — write_strings_xml uses text-based insertion
    so ET does not reformat the entire file on every run.
    """
    tree = ET.parse(strings_path)
    root = tree.getroot()
    existing = {}
    non_translatable = set()
    for string in root.findall('string'):
        name = string.attrib['name']
        existing[name] = string.text
        if string.attrib.get('translatable', 'true').lower() == 'false':
            non_translatable.add(name)
    return existing, non_translatable


def _lookup_or_create(string, existing_values, non_translatable_keys, key_index):
    """Return (key, is_reused), or (None, False) if the string should be skipped."""
    if (not string
            or _is_numeric_like(string)
            or string.startswith(("@", "?"))
            or string.strip() in SKIP_VALUES):
        return None, False
    existing_key = next(
        (k for k, v in existing_values.items() if v == string and k not in non_translatable_keys),
        None,
    )
    if existing_key:
        return existing_key, True
    key = generate_short_key(string, existing_values, key_index)
    existing_values[key] = string
    return key, False


# ---------------------------------------------------------------------------
# XML layout extraction
# ---------------------------------------------------------------------------

def extract_xml_strings(res_dir, existing_values, non_translatable_keys, key_index,
                        dry_run=False, verbose=True):
    new_strings = {}
    # FIX 5: 'xml_files' separates layout files from source files in summary
    stats = {'reused': 0, 'new': 0, 'xml_files': 0}

    for root_dir, _, files in os.walk(res_dir):
        if 'layout' not in root_dir:
            continue
        for file in files:
            if not file.endswith(".xml"):
                continue
            path = os.path.join(root_dir, file)
            try:
                # Read raw content BEFORE parsing so the backup is the true original
                with open(path, 'r', encoding='utf-8') as fh:
                    original_content = fh.read()

                tree = ET.parse(path)
                root = tree.getroot()
                modified = False

                for elem in root.iter():
                    # Track values already handled on this element to avoid double-processing
                    # when both android:text and {ns}text forms are present
                    seen_values_this_elem = set()
                    for attr in COMMON_ATTRS:
                        value = elem.get(attr)
                        if not value or value in seen_values_this_elem:
                            continue
                        if value.startswith(("@", "?")):
                            continue
                        if value.strip() in SKIP_VALUES:
                            continue
                        seen_values_this_elem.add(value)

                        key, is_reused = _lookup_or_create(
                            value, existing_values, non_translatable_keys, key_index
                        )
                        if key is None:
                            continue

                        elem.set(attr, f"@string/{key}")
                        modified = True
                        if is_reused:
                            stats['reused'] += 1
                            if verbose:
                                print(f"    ✔ Reused '{key}' for '{value}' in {file}")
                        else:
                            new_strings[key] = value
                            stats['new'] += 1
                            if verbose:
                                print(f"    + New key '{key}' for '{value}' in {file}")

                if not dry_run and modified:
                    backup_path = f"{path}.bak"
                    with open(backup_path, 'w', encoding='utf-8') as bf:
                        bf.write(original_content)
                    tree.write(path, encoding='utf-8', xml_declaration=True)
                    stats['xml_files'] += 1
                    if verbose:
                        print(f"    ✔ Updated {file}")

            except ET.ParseError as e:
                print(f"  ⚠ Failed to parse {file}: {e}")
            except (IOError, OSError) as e:                      # FIX 6
                print(f"  ⚠ Could not read {file}: {e}")

    return new_strings, stats


# ---------------------------------------------------------------------------
# Java / Kotlin source extraction
# ---------------------------------------------------------------------------

def _make_method_replacer(existing_values, non_translatable_keys, key_index,
                          new_strings, stats, verbose, file, lang_label):
    """re.sub callback for method-call patterns."""
    def replacer(m):
        if m.group(1) is None:      # comment branch — leave unchanged
            return m.group(0)
        prefix, raw_string, closing = m.group(1), m.group(2), m.group(3)
        string = raw_string.strip()
        key, is_reused = _lookup_or_create(
            string, existing_values, non_translatable_keys, key_index
        )
        if key is None:
            return m.group(0)
        if not is_reused:
            new_strings[key] = string
            stats['new'] += 1
            if verbose:
                print(f"    + New key '{key}' for '{string}' in {file} [{lang_label}]")
        else:
            stats['reused'] += 1
            if verbose:
                print(f"    ✔ Reused '{key}' for '{string}' in {file} [{lang_label}]")
        return f'{prefix}getString(R.string.{key}){closing}'
    return replacer


def _make_prop_replacer(existing_values, non_translatable_keys, key_index,
                        new_strings, stats, verbose, file):
    """re.sub callback for Kotlin property-assignment patterns."""
    def replacer(m):
        if m.group(1) is None:      # comment branch — leave unchanged
            return m.group(0)
        prefix, raw_string = m.group(1), m.group(2)
        string = raw_string.strip()
        key, is_reused = _lookup_or_create(
            string, existing_values, non_translatable_keys, key_index
        )
        if key is None:
            return m.group(0)
        if not is_reused:
            new_strings[key] = string
            stats['new'] += 1
            if verbose:
                print(f"    + New key '{key}' for '{string}' in {file} [Kotlin prop]")
        else:
            stats['reused'] += 1
            if verbose:
                print(f"    ✔ Reused '{key}' for '{string}' in {file} [Kotlin prop]")
        return f'{prefix}getString(R.string.{key})'
    return replacer


def extract_source_strings(source_dir, existing_values, non_translatable_keys, key_index,
                            dry_run=False, verbose=True, is_kotlin=False):
    new_strings = {}
    # FIX 5: 'src_files' separates source files from XML layout files in summary
    stats = {'reused': 0, 'new': 0, 'src_files': 0}
    ext = ".kt" if is_kotlin else ".java"
    lang_label = "Kotlin" if is_kotlin else "Java"

    for root, _, files in os.walk(source_dir):
        for file in files:
            if not file.endswith(ext):
                continue
            path = os.path.join(root, file)
            try:                                                  # FIX 6
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except (IOError, OSError) as e:
                print(f"  ⚠ Could not read {file}: {e}")
                continue

            modified = content

            for pattern in METHOD_CALL_PATTERNS:
                modified = pattern.sub(
                    _make_method_replacer(
                        existing_values, non_translatable_keys, key_index,
                        new_strings, stats, verbose, file, lang_label,
                    ),
                    modified,
                )

            if is_kotlin:
                for pattern in KOTLIN_PROP_PATTERNS:
                    modified = pattern.sub(
                        _make_prop_replacer(
                            existing_values, non_translatable_keys, key_index,
                            new_strings, stats, verbose, file,
                        ),
                        modified,
                    )

            if not dry_run and content != modified:
                backup_path = path + ".bak"
                try:                                              # FIX 6
                    with open(backup_path, 'w', encoding='utf-8') as bf:
                        bf.write(content)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(modified)
                    stats['src_files'] += 1
                    if verbose:
                        print(f"    ✔ Updated {file} (backup: {file}.bak)")
                except (IOError, OSError) as e:
                    print(f"  ⚠ Could not write {file}: {e}")

    return new_strings, stats


# ---------------------------------------------------------------------------
# Sync locale files
# ---------------------------------------------------------------------------

# Matches a <string name="KEY">...</string> line (single-line form)
_STRING_LINE_RE = re.compile(r'^[ \t]*<string name="{key}">.*?</string>[ \t]*\r?\n', re.MULTILINE)
# Matches a <!-- TODO: translate --> comment on the line immediately before the string
_TODO_COMMENT_RE = re.compile(r'[ \t]*<!-- TODO: translate -->[ \t]*\r?\n$')
# Extracts raw (already-escaped) text content from <string> elements
_RAW_STRING_RE = re.compile(r'<string\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</string>', re.DOTALL)


def _raw_string_map(strings_path):
    """
    Read strings.xml as plain text and return {name: raw_content} where
    raw_content is the already-escaped element text (e.g. \' or &apos; or
    &amp; exactly as written in the file).

    Using raw text instead of ET avoids double-escaping: ET decodes XML
    entities on read, so re-applying _XML_ESCAPES would encode them again
    (e.g. &apos; → ' → &apos; is fine, but \' → \' + re-escape → \\').
    """
    with open(strings_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return {m.group(1): m.group(2) for m in _RAW_STRING_RE.finditer(content)}


def sync_locale_files(res_dir, strings_path, prune=False, dry_run=False, verbose=True):
    """
    Sync every values-*/strings.xml against the default strings.xml.

    - Missing keys  → appended with the English value + <!-- TODO: translate --> marker.
    - Obsolete keys → removed only when --prune is set.
    - Existing translations are never modified.
    """
    default_strings, _ = load_strings_xml(strings_path)
    # Raw map preserves the original escaping (e.g. \' or &apos;) so values
    # can be copied verbatim to locale files — no re-escaping needed.
    raw_defaults = _raw_string_map(strings_path)
    values_dir = os.path.dirname(strings_path)   # …/res/values
    res        = os.path.dirname(values_dir)      # …/res

    locale_paths = []
    try:
        for entry in sorted(os.listdir(res)):
            if entry.startswith('values-'):
                lp = os.path.join(res, entry, 'strings.xml')
                if os.path.isfile(lp):
                    locale_paths.append((entry, lp))
    except (IOError, OSError) as e:
        print(f"  ⚠ Could not list res directory: {e}")
        return {'locales': 0, 'added': 0, 'removed': 0}

    if not locale_paths:
        print("  ℹ  No locale files found (values-*/strings.xml)")
        return {'locales': 0, 'added': 0, 'removed': 0}

    total_added = total_removed = 0

    for locale_dir, locale_path in locale_paths:
        locale_label = locale_dir[len('values-'):]   # e.g. "ar", "fr-rFR"
        try:
            locale_strings, _ = load_strings_xml(locale_path)
        except (IOError, OSError, ET.ParseError) as e:
            print(f"  ⚠ Could not read {locale_dir}/strings.xml: {e}")
            continue

        missing  = {k: v for k, v in default_strings.items() if k not in locale_strings}
        obsolete = [k for k in locale_strings if k not in default_strings]

        nothing_to_do = not missing and (not prune or not obsolete)
        if nothing_to_do:
            if verbose:
                print(f"    ✔ [{locale_label}] up to date")
            continue

        if verbose:
            print(f"\n    [{locale_label}] {locale_path}")

        # --- Add missing keys ---
        if missing:
            lines = []
            for key in missing:
                # Use the raw (already-escaped) text from strings.xml so we
                # never double-escape (e.g. \' would become \\' via ET).
                raw_value = raw_defaults.get(key, '')
                lines.append('    <!-- TODO: translate -->')
                lines.append(f'    <string name="{key}">{raw_value}</string>')
            insertion = '\n'.join(lines) + '\n'

            if not dry_run:
                try:
                    with open(locale_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    idx = content.rfind('</resources>')
                    new_content = (content[:idx] + insertion + content[idx:]
                                   if idx != -1 else content + '\n' + insertion)
                    with open(locale_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                except (IOError, OSError) as e:
                    print(f"    ⚠ Could not write {locale_dir}/strings.xml: {e}")
                    continue

            total_added += len(missing)
            if verbose:
                for key in missing:
                    print(f"      + Added '{key}' (needs translation)")

        # --- Remove obsolete keys (only when --prune is set) ---
        if prune and obsolete:
            if not dry_run:
                try:
                    with open(locale_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    for key in obsolete:
                        # Remove the <string> line
                        pattern = re.compile(
                            r'^[ \t]*<string name="' + re.escape(key) + r'">.*?</string>[ \t]*\r?\n',
                            re.MULTILINE,
                        )
                        content = pattern.sub('', content)
                        # Remove a preceding <!-- TODO: translate --> comment if present
                        content = re.sub(
                            r'([ \t]*<!-- TODO: translate -->[ \t]*\r?\n)(?=' +
                            r'[ \t]*<!-- TODO: translate -->|[ \t]*</resources>|\Z)',
                            '', content,
                        )
                    with open(locale_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                except (IOError, OSError) as e:
                    print(f"    ⚠ Could not write {locale_dir}/strings.xml: {e}")
                    continue

            total_removed += len(obsolete)
            if verbose:
                for key in obsolete:
                    print(f"      - Removed '{key}' (obsolete)")

    return {'locales': len(locale_paths), 'added': total_added, 'removed': total_removed}


# ---------------------------------------------------------------------------
# Write strings.xml  (FIX 3: text-based insertion — no ET reformat of whole file)
# ---------------------------------------------------------------------------

def write_strings_xml(strings_path, new_strings, dry_run):
    """
    Append new <string> entries to strings.xml by inserting them as raw text
    just before the closing </resources> tag.  This preserves all existing
    formatting and avoids the ET.indent full-file reformat on every run.
    """
    if not new_strings:
        return

    lines = []
    for key, value in new_strings.items():
        escaped = value.translate(_XML_ESCAPES)
        lines.append(f'    <string name="{key}">{escaped}</string>')
    insertion = '\n'.join(lines) + '\n'

    if not dry_run:
        try:
            with open(strings_path, 'r', encoding='utf-8') as f:
                content = f.read()
            idx = content.rfind('</resources>')
            if idx != -1:
                new_content = content[:idx] + insertion + content[idx:]
            else:
                new_content = content + '\n' + insertion
            with open(strings_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except (IOError, OSError) as e:
            print(f"  ⚠ Could not update strings.xml: {e}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cli():
    parser = argparse.ArgumentParser(
        description='Extract hardcoded strings from Android XML layouts and Java/Kotlin source files.',
        allow_abbrev=False,   # prevent --prun silently matching --prune, etc.
    )
    parser.add_argument('--xml',     action='store_true', help='Extract strings from XML layout files')
    parser.add_argument('--java',    action='store_true', help='Extract strings from Java source files')
    parser.add_argument('--kotlin',  action='store_true', help='Extract strings from Kotlin source files')
    parser.add_argument('--sync',    action='store_true', help='Sync all values-*/strings.xml with the default strings.xml')
    parser.add_argument('--prune',   action='store_true', help='Remove obsolete keys from locale files during --sync')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing any files')
    parser.add_argument('--path',    default=None,        help='Android project root (default: current directory)')
    parser.add_argument('--quiet',   action='store_true', help='Suppress per-string output; show summary only')
    args = parser.parse_args()

    if not (args.xml or args.java or args.kotlin or args.sync):
        print("⚠  Please specify at least one of --xml, --java, --kotlin, or --sync.")
        parser.print_help()
        return

    verbose = not args.quiet
    project_dir = os.path.abspath(args.path) if args.path else os.getcwd()

    strings_path = find_strings_xml(project_dir)
    if not strings_path:
        print(f"❌ Could not find strings.xml under {project_dir}")
        return

    try:
        # FIX 3: load_strings_xml no longer returns root element
        existing_keys, non_translatable_keys = load_strings_xml(strings_path)
    except (FileNotFoundError, ET.ParseError) as e:
        print(f"❌ Could not load strings.xml: {e}")
        return

    # Derive src/main from strings_path — works for any module (app/, lib/, feature/, etc.)
    src_main = os.path.normpath(os.path.join(os.path.dirname(strings_path), "..", ".."))

    key_index = [1]
    all_new_strings = {}
    # FIX 5: track XML layout files and source files separately
    total_stats = {'reused': 0, 'new': 0, 'xml_files': 0, 'src_files': 0}

    # --- XML layouts ---
    if args.xml:
        if verbose:
            print("\n📄 Scanning XML layouts...")
        res_dir = os.path.join(src_main, "res")
        if os.path.exists(res_dir):
            xml_strings, stats = extract_xml_strings(
                res_dir, existing_keys, non_translatable_keys, key_index,
                args.dry_run, verbose,
            )
            all_new_strings.update(xml_strings)
            for k in ('reused', 'new', 'xml_files'):
                total_stats[k] += stats[k]
        else:
            print(f"❌ Could not find res directory at {res_dir}")

    # --- Java source ---
    if args.java:
        if verbose:
            print("\n☕ Scanning Java source files...")
        java_dir = os.path.join(src_main, "java")
        if os.path.exists(java_dir):
            java_strings, stats = extract_source_strings(
                java_dir, existing_keys, non_translatable_keys, key_index,
                args.dry_run, verbose, is_kotlin=False,
            )
            all_new_strings.update(java_strings)
            for k in ('reused', 'new', 'src_files'):
                total_stats[k] += stats[k]
        else:
            print(f"❌ Could not find Java source directory at {java_dir}")

    # --- Kotlin source ---
    if args.kotlin:
        if verbose:
            print("\n🎯 Scanning Kotlin source files...")
        # Scan BOTH java/ and kotlin/ — Kotlin files can live in either or both
        kotlin_scanned = False
        for kdir_name in ("java", "kotlin"):
            kdir = os.path.join(src_main, kdir_name)
            if os.path.exists(kdir):
                kotlin_scanned = True
                kt_strings, stats = extract_source_strings(
                    kdir, existing_keys, non_translatable_keys, key_index,
                    args.dry_run, verbose, is_kotlin=True,
                )
                all_new_strings.update(kt_strings)
                for k in ('reused', 'new', 'src_files'):
                    total_stats[k] += stats[k]
        if not kotlin_scanned:
            print(f"❌ Could not find Kotlin source directory under {src_main}")

    # --- Write strings.xml (FIX 3: text-based, no ET full-file reformat) ---
    if all_new_strings:
        write_strings_xml(strings_path, all_new_strings, args.dry_run)

    # --- Sync locale files (runs after extraction so new keys are included) ---
    sync_stats = {'locales': 0, 'added': 0, 'removed': 0}
    if args.sync:
        res_dir = os.path.join(src_main, "res")
        if verbose:
            print("\n🌍 Syncing locale files...")
        if os.path.exists(res_dir):
            sync_stats = sync_locale_files(
                res_dir, strings_path,
                prune=args.prune,
                dry_run=args.dry_run,
                verbose=verbose,
            )
        else:
            print(f"❌ Could not find res directory at {res_dir}")

    # --- Summary ---
    print("\n" + "─" * 48)
    print("📊  Summary")
    print("─" * 48)
    print(f"  New strings extracted  : {total_stats['new']}")
    print(f"  Existing keys reused   : {total_stats['reused']}")
    print(f"  Layout files modified  : {total_stats['xml_files']}")
    print(f"  Source files modified  : {total_stats['src_files']}")
    if args.sync:
        print(f"  Locale files synced    : {sync_stats['locales']}")
        print(f"  Keys added to locales  : {sync_stats['added']}")
        if args.prune:
            print(f"  Obsolete keys removed  : {sync_stats['removed']}")
    if args.dry_run:
        print("\n  [DRY RUN] No files were written.")
        if all_new_strings:
            print("\n  Strings that would be added to strings.xml:")
            for k, v in all_new_strings.items():
                print(f'    {k} = "{v}"')
    elif all_new_strings:
        print(f"\n  ✔ strings.xml updated → {strings_path}")
    print("─" * 48)


if __name__ == "__main__":
    cli()
