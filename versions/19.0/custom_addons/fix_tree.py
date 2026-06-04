import os
import glob
import re

xml_files = glob.glob('d:/Projects/Subscription/**/*.xml', recursive=True)

for file_path in xml_files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Replace <tree... with <list...
    new_content = re.sub(r'<tree(\s|>)', r'<list\1', content)
    # Replace </tree> with </list>
    new_content = re.sub(r'</tree>', r'</list>', new_content)
    # Replace view_mode="tree,form" with view_mode="list,form" (and other combinations)
    new_content = re.sub(r'view_mode\s*=\s*(["\'])(.*?)\b(?:tree)\b(.*?)\1', r'view_mode=\1\2list\3\1', new_content)
    # Also replace view_type="tree" just in case
    new_content = re.sub(r'view_type\s*=\s*(["\'])\b(?:tree)\b\1', r'view_type=\1list\1', new_content)

    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {file_path}")
