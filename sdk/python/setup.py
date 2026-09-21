from setuptools import setup, find_packages

setup(
    name='streamforge',
    version='1.0.0',
    description='Python SDK for StreamForge real-time data pipeline platform',
    author='Nishit Patel',
    license='MIT',
    packages=find_packages(),
    python_requires='>=3.10',
    install_requires=[
        'requests>=2.28.0',
    ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)
