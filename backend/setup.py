from setuptools import setup, find_packages

setup(
    name="app",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "langchain",
        "langchain-core",
        "langchain-community",
        "langgraph",
        "langchain-anthropic",
    ]
) 