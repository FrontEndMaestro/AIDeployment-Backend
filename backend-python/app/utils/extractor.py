import zipfile
import tarfile
import os
from typing import Dict, List
from .file_system import count_items


def extract_zip(zip_path: str, project_id: str, user_workspace: str) -> Dict:
    try:
        extract_path = os.path.join(user_workspace, "extracted", f"project-{project_id}")
        
        if os.path.exists(extract_path):
            import shutil
            shutil.rmtree(extract_path)
        
        os.makedirs(extract_path, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        print(f"✅ ZIP extracted to: {extract_path}")
        
        files_count, folders_count = count_items(extract_path)
        
        return {
            "success": True,
            "extracted_path": extract_path,
            "files_count": files_count,
            "folders_count": folders_count,
            "logs": ["ZIP extraction completed successfully"]
        }
    except Exception as e:
        print(f"❌ ZIP extraction failed: {str(e)}")
        raise Exception(f"ZIP extraction failed: {str(e)}")


def extract_tar(tar_path: str, project_id: str, user_workspace: str) -> Dict:
    try:
        extract_path = os.path.join(user_workspace, "extracted", f"project-{project_id}")
        
        if os.path.exists(extract_path):
            import shutil
            shutil.rmtree(extract_path)
        
        os.makedirs(extract_path, exist_ok=True)
        
        with tarfile.open(tar_path, 'r:*') as tar_ref:
            tar_ref.extractall(extract_path)
        
        print(f"✅ TAR extracted to: {extract_path}")
        
        files_count, folders_count = count_items(extract_path)
        
        return {
            "success": True,
            "extracted_path": extract_path,
            "files_count": files_count,
            "folders_count": folders_count,
            "logs": ["TAR extraction completed successfully"]
        }
    except Exception as e:
        print(f"❌ TAR extraction failed: {str(e)}")
        raise Exception(f"TAR extraction failed: {str(e)}")


def extract_file(file_path: str, project_id: str, user_workspace: str) -> Dict:
    try:
        if not os.path.exists(file_path):
            raise Exception("File not found")
        
        ext = os.path.splitext(file_path)[1].lower()
        
        print(f"📦 Extracting file: {file_path}")
        print(f"📦 File type: {ext}")
        
        if ext == '.zip':
            result = extract_zip(file_path, project_id, user_workspace)
        elif ext in ['.tar', '.gz', '.tgz']:
            result = extract_tar(file_path, project_id, user_workspace)
        else:
            raise Exception(f"Unsupported file type: {ext}")
        
        return result
    except Exception as e:
        print(f"❌ Extraction failed: {str(e)}")
        raise e


def get_files_list(dir_path: str) -> List[Dict]:
    files_list = []
    
    def scan_directory(directory: str, relative_path: str = "", depth: int = 0):
        if depth > 20:
            return
        try:
            items = os.listdir(directory)
            for item in items:
                item_path = os.path.join(directory, item)
                rel_path = os.path.join(relative_path, item)
                
                if os.path.isdir(item_path):
                    files_list.append({
                        "name": item,
                        "path": rel_path,
                        "type": "folder",
                        "size": 0
                    })
                    scan_directory(item_path, rel_path, depth + 1)
                else:
                    files_list.append({
                        "name": item,
                        "path": rel_path,
                        "type": "file",
                        "size": os.path.getsize(item_path),
                        "extension": os.path.splitext(item)[1]
                    })
        except Exception as e:
            print(f"Error scanning directory: {e}")
    
    if os.path.exists(dir_path):
        scan_directory(dir_path)
    
    return files_list


def cleanup_extracted_files(project_id: str, user_workspace: str = None) -> bool:
    try:
        if user_workspace:
            extract_path = os.path.join(user_workspace, "extracted", f"project-{project_id}")
        else:
            extract_path = os.path.join("./extracted", f"project-{project_id}")
        
        if os.path.exists(extract_path):
            import shutil
            shutil.rmtree(extract_path)
            print(f"🗑️ Cleaned up extracted files for project: {project_id}")
            return True
        return False
    except Exception as e:
        print(f"Cleanup error: {e}")
        return False
