from setuptools import setup, find_packages

setup(
    name='strex',
    version='1.1.0',
    packages=find_packages(),
    install_requires=[],
    entry_points={
        'console_scripts': [
            'strex=strex.cli:cli',
        ],
    },
    author='Ahmed Esmat',
    description='Android string extractor — pull hardcoded strings into strings.xml from XML layouts and Java/Kotlin source files.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    license='MIT',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Environment :: Console',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Internationalization',
        'Topic :: Software Development :: Localization',
    ],
    python_requires='>=3.6',
)
