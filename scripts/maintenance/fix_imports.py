import os
import re

def fix_imports():
    root = r"F:\trading system01\trading system\backend"
    
    # Regex to match "from app." and "import app."
    from_pattern = re.compile(r'^(\s*)from app\.(.*? import .*)$')
    import_pattern = re.compile(r'^(\s*)import app\.(.*)$')
    
    modified_files = []
    
    for dirpath, dirnames, filenames in os.walk(root):
        for file in filenames:
            if file.endswith('.py'):
                filepath = os.path.join(dirpath, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                changed = False
                new_lines = []
                for line in lines:
                    if from_pattern.match(line):
                        new_line = from_pattern.sub(r'\1from backend.app.\2', line)
                        new_lines.append(new_line)
                        changed = True
                    elif import_pattern.match(line):
                        new_line = import_pattern.sub(r'\1import backend.app.\2', line)
                        new_lines.append(new_line)
                        changed = True
                    else:
                        new_lines.append(line)
                
                if changed:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    modified_files.append(filepath)
                    print(f"Modified: {filepath}")
                    
    print(f"Total modified files: {len(modified_files)}")

if __name__ == "__main__":
    fix_imports()
