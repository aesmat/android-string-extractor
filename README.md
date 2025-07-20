Install Locally:
pipx uninstall locale-gen
pipx install --editable .


Usage:
locale-gen          # Run extraction
locale-gen --dry-run

To Build a Wheel (Optional):
python setup.py sdist bdist_wheel

Publish:
To TestPyPI: twine upload --repository-url https://test.pypi.org/legacy/ dist/*
To PyPI: twine upload dist/*

