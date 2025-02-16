from setuptools import setup, find_packages

setup(
    name="swarm-backend",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.109.2",
        "uvicorn>=0.27.1",
        "supabase>=1.2.0",
        "python-multipart>=0.0.7",
        "pydantic>=2.6.1",
        "pytest>=8.0.0",
        "pytest-asyncio>=0.23.5",
        "pytest-env>=1.1.3",
    ],
    python_requires=">=3.8",
) 