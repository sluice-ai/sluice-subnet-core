import codecs
import re
from pathlib import Path

from setuptools import find_packages, setup


def read_requirements(path: str) -> list[str]:
    requirements: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        requirements.append(stripped)
    return requirements


here = Path(__file__).resolve().parent
long_description = (here / "README.md").read_text(encoding="utf-8")
requirements = read_requirements(str(here / "requirements.txt"))

with codecs.open(here / "sluice_subnet" / "__init__.py", encoding="utf-8") as init_file:
    version_match = re.search(
        r"^__version__ = ['\"]([^'\"]*)['\"]",
        init_file.read(),
        re.M,
    )
    version_string = version_match.group(1)

setup(
    name="sluice-subnet",
    version=version_string,
    description="Bittensor subnet for competitive AI routing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sluice-labs/sluice-subnet",
    author="Sluice",
    author_email="team@sluice.local",
    packages=find_packages(exclude=("tests", "docs")),
    include_package_data=True,
    license="MIT",
    python_requires=">=3.10",
    install_requires=requirements,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
