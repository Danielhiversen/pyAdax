from setuptools import setup

setup(
    name="adax",
    packages=["adax"],
    install_requires=["aiohttp>=3.0.6", "async_timeout>=3.0.0"],
    version="0.3.0",
    description="A python3 library to communicate with Adax",
    long_description="A python3 library to communicate with Adax",
    python_requires=">=3.5.3",
    author="Daniel Hjelseth Hoyer",
    author_email="mail@dahoiv.net",
    url="https://github.com/Danielhiversen/pyAdax",
    license="MIT",
    classifiers=[
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Home Automation",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
