
#!/bin/bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
venv/bin/python3 -X importtime scripts/test_imports.py 2> import_profile.log
