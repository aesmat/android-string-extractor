from setuptools import setup, find_packages

setup(
    name='locale-gen',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[],
    entry_points={
        'console_scripts': [
            'locale-gen=locale_gen.cli:cli',
        ],
    },
    author='Ahmed Esmat',
    description='Android XML string extractor and translation sync tool',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    license='MIT',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Environment :: Console',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
