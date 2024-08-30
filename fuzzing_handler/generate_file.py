import os
import json
import shutil
from utils.code_utils import CodeUtils

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
prompt_dir = os.path.abspath(os.path.join(project_dir, "llm_interface"))
output_dir = os.path.join(project_dir, "fuzzing_handler", "file_output")
tmp_dir = os.path.join(project_dir, "fuzzing_handler", "tmp")

code_utils = CodeUtils()

if __name__ == "__main__":

    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    
    file_dict = {}
    for assemble_file in sorted(os.listdir(os.path.join(prompt_dir, "output"))):
        if not assemble_file.startswith("assembled_"):
            continue

        name = assemble_file.split("_")[-1][:-5]

        if name not in file_dict.keys():
            file_dict[name] = []
        
        with open(os.path.join(prompt_dir, "output", assemble_file), "r") as f:
            assemble_data = json.loads(f.read()) 
        
        for i, cmd_data in enumerate(assemble_data):

            print(name, i)

            cmd = cmd_data["cmd"]
            placeholders = cmd_data["placeholders"]
            combination_data = cmd_data["combination_data"]
            code = json.loads(cmd_data["code"])
            

            code = code.replace("/tmp", os.path.normpath(tmp_dir)).replace("__file__", f'"{os.path.normpath(tmp_dir)}"')

            code = code_utils.processCodeString(code)

            if code == None:
                continue

            os.chdir(tmp_dir)
            err = code_utils.executePythonCode(code)
            if err == None:

                ret_data = {"id": i, "cmd": cmd, "placeholders": placeholders, "combination_data": combination_data, "files": []}

                cmd_output_path = os.path.join(output_dir, f"{name}_{i}")
                os.makedirs(cmd_output_path, exist_ok=True)

                for root, dirs, files in os.walk(tmp_dir):
                    for filename in files:
                        ret_data["files"].append(os.path.relpath(os.path.join(root, filename), tmp_dir))
                
                if len(ret_data["files"]) == 0:
                    print(f"[x] Empty generated files: {(name, i)}")
                    shutil.rmtree(cmd_output_path)
                    continue

                file_dict[name].append(ret_data)
            
                for item in os.listdir(tmp_dir):
                    shutil.move(os.path.join(tmp_dir, item), os.path.join(cmd_output_path, item))

            shutil.rmtree(tmp_dir)
            os.makedirs(tmp_dir, exist_ok=True)     

    with open(os.path.join(prompt_dir, "output", "file.json"), "w") as f:
        f.write(json.dumps(file_dict, indent=4))