import os
import re
import sys
import copy
import json
import argparse
import demjson3 as demjson
from string import Template
from utils.gpt_utils import GPTUtils
from utils.opt_utils import OptionUtils

gpt_utils = GPTUtils()
option_utils = OptionUtils()

prompt_path = sys.path[0]
project_path = os.path.abspath(os.path.join(prompt_path, ".."))

choice_number = 10
ratio = 0.5

def splitJointOptionsGPT(option_data, model):

    prompt_template  = Template("""

    Given an option and its description,

    ```json
    $data
    ```

    ## Instruction

    Please separate the options listed in the 'option' field and create individual descriptions for each option based on the original description in the 'description' field. Ensure that each new description is specifically tailored to explain the function and use of its corresponding option. If you cannot generate the new description, you can use the original description instead. 

    ## Output

    The output should in JSON format. Maintain the Full Option Pattern in the "option" field as the Key. Here is an example,

    ```json
    {
        "options": {
            "option1": "description of option1",
            "option2": "description of option2"
        }
    }
    ```

    Let's work this out in a step by step way to be sure we have the right answer.

    """)

    prompt = Template.substitute(prompt_template, data=json.dumps(option_data))

    responses = gpt_utils.queryOpenAI(prompt, model=model, temperature=0, n=1)

    for res in responses:

        # Search for JSON pattern in the input string using re.DOTALL to match across multiple lines
        json_list = re.findall(r'```json\s*(\{.*?\})\s*```', res, re.DOTALL)
        for json_str in json_list:
            try:
                json_data = json.loads(json_str)
            except json.decoder.JSONDecodeError:
                json_obj = demjson.decode(json_str)  #fix broken json_str to  json object
                fixed_json_str = demjson.encode(json_obj)
                json_data = json.loads(fixed_json_str)
            if 'options' in json_data:
                ret_option_data = json_data
                break
        if not ret_option_data:
            print("[x] Cannot find json data.")
            exit(1)

        
    return ret_option_data

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='''
        %s - Split joint options and restruct the manpage.
    ''' % sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--file', type=str, help = 'Input manpage file (manapge_%NAME%.json).', required=True)

    args = parser.parse_args()

    manpage_path = args.file

    name = manpage_path.split("_")[-1][:-5]
    
    print(f"[*] Processing {name} ...")

    with open(manpage_path, "r") as f:
        orig_manpage_data = json.loads(f.read())
    
    target_opt_list = []
    for opt in orig_manpage_data["options"]:
        if len(option_utils.splitJointOption(opt)) > 2:
            target_opt_list.append(opt)

    if len(target_opt_list) > 0:
        new_manpage_data = copy.deepcopy(orig_manpage_data)
        for opt in target_opt_list:
            option_data = {"option": opt, "description": orig_manpage_data["options"][opt]}
            new_opt_data = splitJointOptionsGPT(option_data, model="gpt-4-1106-preview")
            del new_manpage_data["options"][opt]
            for new_opt in new_opt_data["options"]:
                new_manpage_data["options"][new_opt] = new_opt_data["options"][new_opt]
        print(f"[INFO] {name} has been modified!")

        output_file_path = os.path.join(prompt_path, "input", f"manpage_{name}.json")
        with open(output_file_path, "w") as f:
            f.write(json.dumps(new_manpage_data))
    
    else:
        output_file_path = os.path.join(prompt_path, "input", f"manpage_{name}.json")
        with open(output_file_path, "w") as f:
            f.write(json.dumps(orig_manpage_data))

    print(f"[OK] Done! The output is saved in {output_file_path}.")
