from setuptools import setup, find_packages

setup(
    name="mail-classifier",
    version="2.0.0",
    description="AI-powered email classification for Outlook",
    author="Your Name",
    packages=find_packages(),
    install_requires=[
        'pywin32>=305',
        'openai>=1.0.0',
        'httpx>=0.25.0',
    ],
    entry_points={
        'console_scripts': [
            'mail-classifier=main:main',
        ],
    },
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
