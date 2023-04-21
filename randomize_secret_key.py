import os
import random
import string

with open("config.py", "r+") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "SECRET_KEY =" in line:
        random_string = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        lines[i] = f'    SECRET_KEY = os.environ.get("SECRET_KEY") or "{random_string}"\n'

with open("config.py", "w") as f:
    f.writelines(lines)
