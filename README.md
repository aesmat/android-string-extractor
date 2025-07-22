# Android String Extractor

This Python package, `locale-gen`, automates the extraction of hardcoded strings from Android XML layout files and Java source code, moving them to the `strings.xml` resource file for better localization and maintainability. It also supports translation synchronization for Android projects.

## Features
- Extracts strings from XML layout attributes (`android:text`, `android:hint`, `android:contentDescription`).
- Extracts strings from `.setText()` calls in Java source files.
- Generates concise, meaningful string keys, avoiding duplicates.
- Reuses existing keys in `strings.xml` when possible.
- Creates backups of modified files.
- Supports dry-run mode to preview changes without modifying files.
- Skips invalid or empty strings (e.g., "", "---", "...").

## Prerequisites
- Python 3.6 or higher.
- Required Python libraries: `xml.etree.ElementTree`, `argparse`, `re` (all included in the standard library).
- `pipx` for local installation (recommended).
- `setuptools` and `wheel` for building a wheel (optional).

## Installation
1. Clone or download this repository to your project directory.
2. Ensure your Android project follows the standard structure:
   - XML layouts in `app/src/main/res/layout/`
   - Java source files in `app/src/main/java/`
   - String resources in `app/src/main/res/values/strings.xml`
3. Install the package locally using `pipx`:
   ```bash
   pipx uninstall locale-gen  # Remove any existing installation
   pipx install --editable .
   ```
   The `--editable` flag allows you to make changes to the script without reinstalling.
4. After installation, the `locale-gen` command is available globally via `pipx`.

## Building a Wheel (Optional)
To create a distributable wheel package:
```bash
python setup.py sdist bdist_wheel
```
This generates a wheel file in the `dist/` directory, which can be installed using `pip` or `pipx`.

## Usage
Run the `locale-gen` command from your Android project's root directory with the following arguments:

```bash
locale-gen [--xml] [--java] [--dry-run]
```

### Arguments
- `--xml`: Extract strings from XML layout files.
- `--java`: Extract strings from Java `.setText()` calls.
- `--dry-run`: Preview changes without modifying files.

At least one of `--xml` or `--java` must be specified.

### Examples
1. Extract strings from XML layouts only:
   ```bash
   locale-gen --xml
   ```

2. Extract strings from both XML and Java files:
   ```bash
   locale-gen --xml --java
   ```

3. Preview changes without modifying files:
   ```bash
   locale-gen --xml --java --dry-run
   ```

## How It Works
1. **Locate `strings.xml`**: The script searches for `strings.xml` in `app/src/main/res/values/`.
2. **Load Existing Strings**: Parses `strings.xml` to track existing keys and avoid duplicates.
3. **Extract Strings**:
   - For XML: Scans layout files for `android:text`, `android:hint`, and `android:contentDescription` attributes, replacing hardcoded values with `@string/key` references.
   - For Java: Scans `.java` files for `.setText("...")` calls, replacing them with `getString(R.string.key)`.
4. **Generate Keys**: Creates concise keys from the string content, omitting common words (e.g., "the", "and") and appending numbers for uniqueness if needed.
5. **Update Files**:
   - Modifies XML/Java files with string references.
   - Appends new strings to `strings.xml`.
   - Creates `.bak` backup files for modified files.
6. **Dry Run**: If enabled, logs changes without writing to files.

## Output
- Modified XML/Java files with string references.
- Updated `strings.xml` with new `<string>` entries.
- Backup files (`*.bak`) for all modified files.
- Console output indicating reused keys, new strings, and file updates.

## Example Output
```bash
✔ Reused existing key 'welcome_message' for value 'Welcome to the app' in activity_main.xml
✔ Updated activity_main.xml (backup: activity_main.xml.bak)
✔ Found 3 new strings.
✔ Updated app/src/main/res/values/strings.xml
```

## Notes
- The script skips strings that are empty, numeric, or start with `@` or `?`.
- Common words (e.g., "the", "and") are excluded from generated keys to keep them concise.
- Backups ensure you can revert changes if needed.
- Always review changes, especially in complex projects, to ensure correctness.

## Limitations
- Only processes `android:text`, `android:hint`, and `android:contentDescription` for XML.
- Only processes `.setText()` calls for Java; other string usages (e.g., `Toast.makeText()`) are not handled.
- Assumes a standard Android project structure.
- Does not handle Kotlin files or non-standard XML attributes.

## Author
Ahmed Esmat

## License
MIT License. Feel free to use and modify as needed.

## Publish
To TestPyPI: twine upload --repository-url https://test.pypi.org/legacy/ dist/*
To PyPI: twine upload dist/*

