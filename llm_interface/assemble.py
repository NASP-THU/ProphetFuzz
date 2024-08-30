import os
import re
import sys
import json
import tqdm
import shutil
import datetime
import argparse
import demjson3 as demjson
from string import Template
from utils.gpt_utils import GPTUtils
from utils.opt_utils import OptionUtils

gpt_utils = GPTUtils()
option_utils = OptionUtils()

prompt_path = sys.path[0]
project_path = os.path.abspath(os.path.join(prompt_path, ".."))

choice_number_maximum = 10
choice_number_per_option = 3

def generateCommands(manpage_data, combinations_data, model):

    prompt_template  = Template("""

    Here is the document of "$name",

    ```json
    $data
    ```

    ## Instruction

    Please combine all of $options based on the "options", and construct a single, definitive command as instructed by the "synopsis" fields. Then supply Python code capable of generating all the specified placeholder files listed in the command configuration data, avoiding dummy file and ensuring that each file contains valid and actual content. 
    
    1. **Option Assembly**: Assemble the required options to create a singular, exclusive command as directed by the "synopsis" field. Confirm the inclusion of all options specified in the "Instruction" section, ensuring nothing is overlooked. Considering the use of this command as input for fuzzers which do not support merged commands, refrain from joining multiple commands using conjunctions like '&&' or ';'.
    2. **Identifying Options for Value Assignment**: Pinpoint options that require values by reviewing their descriptions in the "options" field and confirming with the "synopsis" field. Ensure you do not reference the context of other command-line tools.
    3. **Generating Option Values**: Comprehend the combination's intent, and generate valid values for these options. When these values are strings, surround them with quotation marks and keep them short and relevant, avoiding unnecessary length. For options involving generating output files (instead of reading files), use unique paths in the "/tmp" directory as their values, like "/tmp/{output_filename}.{extension}".
    4. **Placeholder Replacement in Commands**: Replace all placeholders in your command with actual, specific values. This is crucial for elements like scripts, matching rules, or filter rules. When in doubt, opt for credible hypothetical values out of thin air. Refrain from using vague placeholders that demand further action from the user.
    5. **File Specification**: Use the 'file0.{extension}' placeholder to indicate the input file path in your command. Since fuzzers work with one file at a time, ensure you're only using one input file. For other options that require an existing file (excluding output files), utilize placeholders like 'file1.{extension}', 'file2.{extension}', etc., without altering them. If the number of required files is not specific, use just one placeholder. Return a list of placeholders in the results. 
    6. **File Placeholder Integration and Verification**: Check that each file placeholder is correctly used in your command. Remove any placeholders that don't correspond to actual files.
    7. **File Generation Script Development**: Develop a Python script to generate each specified file placeholder out of thin air. Ensure the script is compatible with a 64-bit Ubuntu environment, assuming all necessary dependencies are already installed. Follow these instructions:
        1. Identify the format of the target files. For handling files with complex formats (e.g., binary files), it's advisable to use Python libraries you're familiar with, or to integrate external tools using the 'subprocess' module, to create the most suitable files.
        2. Carefully consider content constraints, guaranteeing their semantic coherence with other defined option values. Notably, the 'file0.{extension}' placeholder should act as an initial seed for fuzzing processes, representing a minimal yet valid test case while ensuring the most extensive feature exposure possible. Under 1 kB is ideal, although not strictly necessary.
        3. Replace all placeholders with specific, pre-determined values. Avoid using any vague placeholders or dummy file that necessitate user input. 
        4. Name each created file using the format '{placeholder}.{extension}' and store them in the current working directory ('./'). Do not execute any final command.
    
    ### Output Format
    Provide the final result of commands in JSON format with no comments, strictly adhering to JSON format standards. Guarantee that the result includes only one, independent command, excising any supplementary or repetitive commands. Confirm that 'file0.{extension}', 'file1.{extension}', 'file2.{extension}', etc., match the placeholders used in the command and reflect the correct count. Provide the Python script in a markdown code block behind the JSON results. 
        
    Here is an example.
    ```json
    {
        "cmd" : "Your specified command with precise option values",
        "placeholders": [
            "file0.{extension}", "file1.{extension}", "file2.{extension}"
        ]
    }
    ```

    ```python
    [Your Code to generate files]
    ```

    Let's work this out in a step by step way to be sure we have the right answer.

    """)

    command_data_list = []

    # Sort by the frequency
    sorted_id_list = sorted(range(len(combinations_data["count"])), key=lambda k: combinations_data["count"][k], reverse=True)
    sorted_combination_list = [combinations_data["combinations"][id] for id in sorted_id_list]

    key_mapping_dict = option_utils.getKeyMappingDict(manpage_data["options"])

    cmd_set = set()
    for com in tqdm.tqdm(sorted_combination_list):

        simplified_manpage_data = {"name": manpage_data["name"], "description": manpage_data["description"], "options": {}, "synopsis": manpage_data["synopsis"]}
        
        valued_option_list = []
        for opt in com:
            for orig_opt in manpage_data["options"]:
                if orig_opt == opt:
                    simplified_manpage_data["options"][orig_opt] = manpage_data["options"][orig_opt]
                    # Add all options in the opt's description
                    for potential_opt in option_utils.findPotentialOptionKeys(manpage_data["options"][opt], key_mapping_dict):
                        simplified_manpage_data["options"][potential_opt] = manpage_data["options"][potential_opt]
                else:
                    # Find all options in each option's description
                    for potential_opt in option_utils.findAllOptions(manpage_data["options"][orig_opt]):
                        # Restore the name and check if opt is equal to it
                        if opt in option_utils.findPotentialOptionKeys(potential_opt, key_mapping_dict):
                            simplified_manpage_data["options"][orig_opt] = manpage_data["options"][orig_opt]
            
            for splitted_opt in option_utils.splitJointOption(opt):
                if option_utils.checkValuedField(splitted_opt):
                    valued_option_list.append(opt)
                    break
                    
        options_string = '"' + '", "'.join([option_utils.splitJointOption(opt)[0] for opt in com]) + '"'

        prompt = Template.substitute(prompt_template, name=manpage_data["name"], data=json.dumps(simplified_manpage_data), options=options_string)

        choice_number = len(valued_option_list) * choice_number_per_option if len(valued_option_list) > 0 else 1
        
        # For Filter_expression
        if manpage_data["name"] == "jq":
            choice_number += 1

        responses = gpt_utils.queryOpenAI(prompt, model, temperature=0.7, n=choice_number)
        
        for res in responses:
            json_list = re.findall(r'```json\s*(\{.*?\})\s*```', res, re.DOTALL)
            command_data = {}
            for json_str in json_list[::-1]:
                try:
                    json_data = json.loads(json_str)
                except json.decoder.JSONDecodeError:
                    try:
                        json_obj = demjson.decode(json_str)  #fix broken json_str to  json object
                        fixed_json_str = demjson.encode(json_obj)
                        json_data = json.loads(fixed_json_str)
                    except demjson.JSONException:
                        continue
                if 'cmd' in json_data:
                    command_data = json_data
                    break

            if len(command_data.keys()) == 0:
                print("[x] Cannot find json data.")
                # exit(1)
                
            if "placeholders" not in command_data.keys() or len(command_data["placeholders"]) == 0:
                print("[INFO] Filtering invalid command without input file.")
                continue

            # Deduplication
            if command_data["cmd"] in cmd_set:
                continue
            cmd_set.add(command_data["cmd"])

            python_list = re.findall(r'```python([\s\S]*?)```', res, re.DOTALL)
            for python_code in python_list[::-1]:
                command_data["code"] = json.dumps(python_code)
                break

            if "code" not in command_data.keys():
                print("[x] Cannot find code data.")
                # exit(1)

            command_data['combination_data'] = com
            command_data_list.append(command_data)

    return command_data_list
    
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='''
        %s - Assemble command based on the combination file and save as a list.
    ''' % sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--file', type=str, help = 'Input manpage file (manapge_%NAME%.json).', required=True)

    args = parser.parse_args()

    manpage_path = args.file

    name = manpage_path.split("_")[-1][:-5]

    print(f"[*] Processing {name} ...")

    with open(manpage_path, "r") as f:
        orig_manpage_data = json.loads(f.read())
    with open(os.path.join(prompt_path, "output", f"predicted_combinations_{name}.json"), "r") as f:
        combinations_data = json.loads(f.read())

    orig_manpage_data = {"name": name, **orig_manpage_data}

    print(f"[*] Assembling executable commands based on {manpage_path} ...")

    command_data_list = generateCommands(orig_manpage_data, combinations_data, model="gpt-4-1106-preview")
       
    output_file_path = os.path.join(prompt_path, "output", f"assembled_command_{name}.json")
    with open(output_file_path, "w") as f:
        f.write(json.dumps(command_data_list))

    print(f"[OK] Done! The output is saved in {output_file_path}.")
    
    