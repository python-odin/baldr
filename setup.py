from setuptools import setup, find_packages

try:
    long_description = open("README.rst").read()
except IOError:
    long_description = ""

setup(
    name='baldr',
    version='0.4.5',
    url='https://github.com/timsavage/baldr',
    license='LICENSE',
    author='Tim Savage',
    author_email='tim.savage@poweredbypenguins.org',
    description='Odin integration to Django',
    long_description=long_description,
    packages=find_packages(exclude=("django_test_runner",)),
    install_requires=['six', 'odin>=0.5', 'django>=1.5'],

    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
