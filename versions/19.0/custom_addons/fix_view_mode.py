import os
import glob
import re

# Fix XML files
xml_files = glob.glob('d:/Projects/Subscription/**/*.xml', recursive=True)
for file_path in xml_files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Replace <field name="view_mode">tree,form</field> with list
    new_content = re.sub(r'<field name="view_mode">(.*?)\btree\b(.*?)</field>', r'<field name="view_mode">\g<1>list\g<2></field>', content)

    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated view_mode in {file_path}")

# Fix Python files
py_files = glob.glob('d:/Projects/Subscription/**/*.py', recursive=True)
for file_path in py_files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Replace 'view_mode': 'list,form' with list
    new_content = re.sub(r"'view_mode':\s*'tree,form'", "'view_mode': 'list,form'", content)
    new_content = re.sub(r'"view_mode":\s*"tree,form"', '"view_mode": "list,form"', new_content)

    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated view_mode in {file_path}")
