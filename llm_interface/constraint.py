import os
import re
import sys
import math
import json
import tqdm
import argparse
import itertools
import networkx as nx
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

def simplifyConflictList(conflict_list, manpage_data):

    ret_conflict_list = []

    key_mapping_dict = option_utils.getKeyMappingDict(manpage_data["options"])

    # Deduplicate
    unique_conflict_list = []
    for sub_list in conflict_list:
        if sorted(sub_list) not in unique_conflict_list:
            unique_conflict_list.append(sorted(sub_list))

    for conflict_pair in unique_conflict_list:
        if any(not item.startswith('-') for item in conflict_pair):
            continue
        alias_list_list = []
        for item in conflict_pair:
            splitted_key_list = option_utils.splitJointOption(item)

            alias_list = []
            if len(splitted_key_list) >= 1:
                for splitted_key in splitted_key_list:
                    if splitted_key not in manpage_data["options"]:
                        alias_list += option_utils.findPotentialOptionKeys(splitted_key, key_mapping_dict)
                    else:
                        alias_list += [splitted_key]

            if len(alias_list) == 0:
                print(f"[Warn] Cannot find the name of {item}")
                break
            alias_list_list.append(alias_list)
        # Contain invalid option
        if len(alias_list_list) != len(conflict_pair):
            continue

        for tuple in itertools.product(*alias_list_list):
            if len(set(tuple)) < 2:
                continue
            if sorted(list(set(tuple))) in ret_conflict_list:
                continue
            ret_conflict_list.append(sorted(list(set(tuple))))

    return ret_conflict_list

def simplifyDependencyList(dependency_list, manpage_data):

    ret_dependency_dict = {}

    key_mapping_dict = option_utils.getKeyMappingDict(manpage_data["options"])

    for dependency_key, dependency_value in dependency_list:
        if not dependency_key.startswith("-") or not dependency_value.startswith("-"):
            continue

        key_list = []
        splitted_key_list = []
        # {"-segment-name||-segment-ext||-segment-timeline": "-dash||-dash-live"}
        if "||" in dependency_key:
            for key in dependency_key.split("||"):
                splitted_key_list += option_utils.splitJointOption(key)
        else:
            splitted_key_list = option_utils.splitJointOption(dependency_key)

        splitted_key_list = list(set(splitted_key_list))

        if len(splitted_key_list) >= 1:
            for splitted_key in splitted_key_list:
                if splitted_key not in manpage_data["options"]:
                    key_list += option_utils.findPotentialOptionKeys(dependency_key, key_mapping_dict)
                else:
                    key_list += [splitted_key]
        else:
            continue

        if "&&" in dependency_value and "||" in dependency_value:
            print(f"[Warn] Complex dependency value with bith && and ||: {dependency_value}")
            continue
        if "&&" in dependency_value:
            pattern = "&&"
        elif "||" in dependency_value:
            pattern = "||"
        else:
            # Meaningless pattern to prevent split
            pattern = "%#!@$!@#!@$^^#@"

        dep_key_list_list = []
        for dep_opt in dependency_value.split(pattern):
            if not dep_opt.startswith("-"):
                break
            dep_opt = dep_opt.strip()
            if dep_opt in manpage_data["options"]:
                dep_key_list = [dep_opt]
            else:
                dep_key_list = option_utils.findPotentialOptionKeys(dep_opt, key_mapping_dict)
            if len(dep_key_list) == 0:
                break
            dep_key_list_list.append(dep_key_list)
        
        # Contain invalid option
        if len(dep_key_list_list) != len(dependency_value.split(pattern)):
            continue

        new_value_list = []
        for tuple in itertools.product(*dep_key_list_list):
            if len(set(tuple)) != len(tuple):
                continue
            new_value_list.append(f"{pattern}".join(sorted(list(tuple))))
        
        for new_key, new_value in itertools.product(key_list, new_value_list):
            if new_key in new_value.split(f"{pattern}"):
                continue

            # Remain each unique key-value pair
            while True:
                if new_key in ret_dependency_dict:
                    if ret_dependency_dict[new_key] != new_value:
                        new_key += "_"
                    else:
                        break
                else:
                    ret_dependency_dict[new_key] = new_value
                    break
    return ret_dependency_dict

def extractRelationships(manpage_data, model):


    # We set the prompt `Assume each option can only be used once in one command.` to avoid value conflict
    prompt_template  = Template("""

    Here is the document of "%s"

    ```json
    $data
    ```

    ## Instruction

    Assume each option can only be used once in one command. Please find any options that are mutually exclusive or logically conflicting when selected together, and find any options that have dependencies on other options.

    ## Output Format

    The output must be in JSON format with no comments and meet the following requirements:

    - Organize conflicting options into an array of arrays, with each sub-array encapsulating a group of options that cannot be used together.
    - For dependencies, use the option that requires others (e.g., "-c") as the key, and its dependencies (e.g., "-d&&-e") as the value. Single dependencies should be listed alone as the value. For multiple simultaneous dependencies, concatenate them using "&&". For independent options that can be used in place of each other, link them with "||". Both the key and the value should be specified in terms of options.
    - In cases where no such relationship exists, leave the value empty but retain the key.
    - Ensure that the output strictly conforms to JSON format standards and is complete without any omissions. Avoid using comments or placeholders in the JSON output.

    Here is an example:
    ```json
    {
    "conflict": [["-a", "-b"]],
    "dependency": {"-c": "-d&&-e"}
    }
    ```

    Let's work this out in a step by step way to be sure we have the right answer.

    """ % (manpage_data["name"]))

    prompt = Template.substitute(prompt_template, data=json.dumps(manpage_data))

    key_mapping_dict = option_utils.getKeyMappingDict(manpage_data["options"])

    ret_relationships = {'conflict': [], 'dependency': {}}

    responses = gpt_utils.queryOpenAI(prompt, model=model, temperature=0.7, n=choice_number)

    conflict_list = []
    dependency_list = []
    for res in responses:

        # Search for JSON pattern in the input string using re.DOTALL to match across multiple lines
        json_list = re.findall(r'```json\s*(\{.*?\})\s*```', res, re.DOTALL)
        for json_str in json_list:
            json_str = json_str.replace("...\n", "")
            try:
                json_data = json.loads(json_str)
            except json.decoder.JSONDecodeError:
                json_obj = demjson.decode(json_str)  #fix broken json_str to  json object
                fixed_json_str = demjson.encode(json_obj)
                json_data = json.loads(fixed_json_str)
            if 'conflict' in json_data or 'dependency' in json_data:
                relationships = json_data
                break
        if not relationships:
            print("[x] Cannot find json data.")
            exit(1)

        if "conflict" in relationships:
            conflict_list += relationships["conflict"]

        if "dependency" in relationships:
            for dependency_key, dependency_value in relationships["dependency"].items():
                dependency_list.append((dependency_key, dependency_value))

    ret_relationships["conflict"] = simplifyConflictList(conflict_list, manpage_data)
    ret_relationships["dependency"] = simplifyDependencyList(dependency_list, manpage_data)

    return ret_relationships

def queryAnswers(option_data, questions, model="gpt-4"):
    
    prompt_template = Template("""
    Given the descriptions of several options,

    ```json
    $data
    ```

    ## Instruction

    Please answer the following questions:
    $questions
                               
    Answer each question sequentially. Respond with 'yes' only if all conditions are met, and 'no' if any are partially or not met.

    ## Output Format

    The output must be in JSON format with no comments, and strictly adhere to JSON format standards. Here is an example:
    ```json
    [
        "yes", "no"
    ]
    ```

    Let's work this out in a step by step way to be sure we have the right answer.
    """)

    questions_text = ""
    i = 1
    for question in questions:
        questions_text += f"{i}. {question}\n    "
        i += 1

    prompt = Template.substitute(prompt_template, data=option_data, questions=questions_text)

    responses = gpt_utils.queryOpenAI(prompt, model=model, temperature=0.2, n=choice_number)

    answers = []
    for res in responses:
    
        # Search for JSON pattern in the input string using re.DOTALL to match across multiple lines
        check_result = re.search(r'```json\s*(\[.*?\])\s*```', res, re.DOTALL).group(1)
        answers.append(json.loads(check_result))

    return answers

def checkRelationships(manpage_data, relationships, model="gpt-4"):
    option_data = {}

    ret_relationships = {'conflict': [], 'dependency': {}}

    relationships_count = len(relationships["conflict"]) + len(relationships["dependency"].keys())

    progress_bar = tqdm.tqdm(total=relationships_count)

    immediate_conflict_list = []

    for conflict_pair in relationships["conflict"]:
        option_data = {}
        used_options = []
        # We've normalized the key in extractRelationships()
        for opt in conflict_pair:
            if opt not in option_data:
                option_data[opt] = manpage_data["options"][opt]
            used_options.append(opt)

        if len(used_options) != len(conflict_pair):
            continue
        
        if len(used_options) == 2:
            positive_question = f'Must "{used_options[0]}" be used without "{used_options[1]}"?'
            negative_question = f'Can "{used_options[0]}" be used with "{used_options[1]}"?'
        elif len(used_options) > 2:
            positive_question = 'Must any two or more of the options ' + ', '.join([f'"{opt}"' for opt in used_options[:-1]]) +  ', and ' + f'"{used_options[-1]}" not be used together?'
            negative_question = 'Can any two or more of the options ' + ', '.join([f'"{opt}"' for opt in used_options[:-1]]) + ', and ' + f'"{used_options[-1]}" be used together?'
        else:
            continue
        
        answers = queryAnswers(option_data, [positive_question, negative_question], model=model)

        correct_count = sum(row == ["yes", "no"] for row in answers)
        if correct_count >= math.ceil(choice_number * ratio):
            immediate_conflict_list.append(conflict_pair)
        
        progress_bar.update(1)
    
    # Simplify
    conflict_list_2D = []
    for conflict_pair in immediate_conflict_list:
        for pair in itertools.combinations(conflict_pair, 2):
            if sorted(pair) not in conflict_list_2D:
                conflict_list_2D.append(sorted(pair))
    
    # We find all maximum cliques to reduce the number of conflict pairs
    G = nx.Graph()

    for pair in conflict_list_2D:
        G.add_edge(pair[0], pair[1])

    ret_relationships["conflict"] = [sorted(pair) for pair in nx.find_cliques(G)]
    
    # We've normalized the key in extractRelationships()
    for dependency_key, dependency_value in relationships["dependency"].items():
        option_data = {}
        
        while dependency_key.endswith("_"):
            dependency_key = dependency_key[:-1]

        if dependency_key not in option_data:
            option_data[dependency_key] = manpage_data["options"][dependency_key]
        subj_option = dependency_key

        if "&&" in dependency_value and "||" in dependency_value:
            print(f"[Warn] Complex dependency value with bith && and ||: {dependency_value}")
            continue
        elif "&&" in dependency_value:
            revolved_options = dependency_value.split("&&")
            conj = "and"
        elif "||" in dependency_value:
            revolved_options = dependency_value.split("||")
            conj = "or"
        else:
            revolved_options = [dependency_value]

        obj_options = []
        for opt in revolved_options:
            if opt not in option_data:
                option_data[opt] = manpage_data["options"][opt]
            obj_options.append(opt)

        if len(obj_options) == 1:
            positive_question = f'Must "{subj_option}" be used with "{obj_options[0]}"?'
            negative_question = f'Can "{subj_option}" be used without "{obj_options[0]}"?'
        elif len(revolved_options) == 2:
            positive_question = f'Must "{subj_option}" be used with "{obj_options[0]}" {conj} "{obj_options[1]}"?'
            negative_question = f'Can "{subj_option}" be used without "{obj_options[0]}" {conj} "{obj_options[1]}"?'
        elif len(revolved_options) > 2:
            positive_question = f'Must "{subj_option}" be used with ' + ', '.join([f'"{opt}"' for opt in obj_options[:-1]]) + f'{conj} "{obj_options[-1]}"?'
            negative_question = f'Can "{subj_option}" be used without ' + ', '.join([f'"{opt}"' for opt in obj_options[:-1]]) + f'{conj} "{obj_options[-1]}"?'
        else:
            continue

        answers = queryAnswers(option_data, [positive_question, negative_question], model=model)

        correct_count = sum(row == ["yes", "no"] for row in answers)
        if correct_count >= math.ceil(choice_number * ratio):
            ret_relationships['dependency'][dependency_key] = dependency_value
        
        progress_bar.update(1)
    
    progress_bar.close()

    return ret_relationships

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='''
        %s - Extract relationships and save as json file.
    ''' % sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--file', type=str, help = 'Input manpage file (manapge_%NAME%.json).', required=True)

    args = parser.parse_args()

    manpage_path = args.file

    name = manpage_path.split("_")[-1][:-5]
    
    print(f"[*] Processing {name} ...")

    print(f"[*] Extracting relationships based on {manpage_path} ...")
    with open(manpage_path, "r") as f:
        orig_manpage_data = json.loads(f.read())
    
    orig_manpage_data = {"name": name, **orig_manpage_data}
    
    ret_relationships = extractRelationships(orig_manpage_data, model="gpt-4-1106-preview")

    output_file_path = os.path.join(prompt_path, "output", f"unchecked_relationships_{name}.json")
    with open(output_file_path, "w") as f:
        f.write(json.dumps(ret_relationships))

    print(f"[*] Checking predicted relationships ...")
    checked_relationships = checkRelationships(orig_manpage_data, ret_relationships, model="gpt-4-1106-preview")

    output_file_path = os.path.join(prompt_path, "output", f"checked_relationships_{name}.json")
    with open(output_file_path, "w") as f:
        f.write(json.dumps(checked_relationships))

    print(f"[OK] Done! The output is saved in {output_file_path}.")
