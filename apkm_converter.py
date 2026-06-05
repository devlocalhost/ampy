import os
import zipfile
import shutil
import sys

def extract_base_apk(bundle_path: str, output_dir: str = "."):
    """
    Extracts the base.apk from an .apkm or .apks archive.
    """
    if not zipfile.is_zipfile(bundle_path):
        print(f"Error: {bundle_path} is not a valid zip archive.")
        return None

    extracted_path = None
    with zipfile.ZipFile(bundle_path, 'r') as zip_ref:
        base_apk_names = [name for name in zip_ref.namelist() if "base.apk" in name.lower()]
        
        target_name = None
        if base_apk_names:
            target_name = base_apk_names[0]
        else:
            apks = [name for name in zip_ref.namelist() if name.endswith('.apk')]
            if len(apks) == 1:
                target_name = apks[0]
            elif apks:
                non_splits = [n for n in apks if "split" not in n.lower() and "config" not in n.lower()]
                if non_splits:
                    target_name = non_splits[0]
                else:
                    target_name = apks[0]
                    
        if target_name:
            print(f"Found base APK candidate: {target_name} inside the bundle.")
            zip_ref.extract(target_name, path=output_dir)
            extracted_path = os.path.join(output_dir, target_name)
            
            base_name = os.path.basename(bundle_path)
            new_name = os.path.splitext(base_name)[0] + "_base.apk"
            new_path = os.path.join(output_dir, new_name)
            
            if os.path.abspath(extracted_path) != os.path.abspath(new_path):
                shutil.move(extracted_path, new_path)
            
            print(f"Successfully extracted base APK to {new_path}")
            return new_path
        else:
            print("Could not find a base APK inside the bundle.")
            return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apkm_converter.py <file.apkm>")
        sys.exit(1)
        
    extract_base_apk(sys.argv[1])
