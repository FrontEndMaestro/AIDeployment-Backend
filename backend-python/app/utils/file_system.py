import os
import shutil
from pathlib import Path
from typing import Optional, Tuple


def file_exists(file_path: str) -> bool:
    return os.path.exists(file_path) and os.path.isfile(file_path)


def directory_exists(dir_path: str) -> bool:
    return os.path.exists(dir_path) and os.path.isdir(dir_path)


def create_directory(dir_path: str) -> bool:
    try:
        os.makedirs(dir_path, exist_ok=True)
        print(f"📁 Directory created: {dir_path}")
        return True
    except Exception as e:
        print(f"Error creating directory: {e}")
        return False


def delete_directory(dir_path: str) -> bool:
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            print(f"🗑️ Directory deleted: {dir_path}")
            return True
        return False
    except Exception as e:
        print(f"Error deleting directory: {e}")
        return False


def delete_file(file_path: str) -> bool:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ File deleted: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error deleting file: {e}")
        return False


def get_file_size(file_path: str) -> int:
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0
    except Exception as e:
        print(f"Error getting file size: {e}")
        return 0


def format_file_size(bytes_size: int) -> str:
    if bytes_size == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(bytes_size)
    unit_index = 0
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def get_directory_size(dir_path: str) -> int:
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(dir_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                total_size += os.path.getsize(filepath)
    except Exception as e:
        print(f"Error calculating directory size: {e}")
    return total_size


def count_items(dir_path: str) -> Tuple[int, int]:
    files_count = 0
    folders_count = 0
    try:
        for root, dirs, files in os.walk(dir_path):
            files_count += len(files)
            folders_count += len(dirs)
    except Exception as e:
        print(f"Error counting items: {e}")
    return files_count, folders_count


def read_file(file_path: str) -> Optional[str]:
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None


def write_file(file_path: str, content: str) -> bool:
    try:
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ File written: {file_path}")
        return True
    except Exception as e:
        print(f"Error writing file: {e}")
        return False


def get_file_extension(file_path: str) -> str:
    return Path(file_path).suffix.lower()


def get_file_name(file_path: str) -> str:
    return Path(file_path).stem