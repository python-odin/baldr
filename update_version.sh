#!/bin/bash
# Quick script to aid the updating of version numbers across the library, setup.py and documentation

sed -i "s/version='[.0-9]*'/version='$1'/g" setup.py
sed -i "s/__version__ = \"[.0-9]*\"/__version__ = \"$1\"/g" baldr/__init__.py
