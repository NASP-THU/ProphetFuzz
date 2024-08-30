import os
import sys
import copy
import json
from string import Template
from utils.gpt_utils import GPTUtils

gpt_utils = GPTUtils()

choice_number = 1

model = "gpt-4-1106-preview"

prompt_path = sys.path[0]
project_path = os.path.abspath(os.path.join(prompt_path, ".."))

choice_number = 1

def generatePrompt(manpage_data, model, choice_number):

    new_manpage_data = copy.deepcopy(manpage_data)
    del new_manpage_data["combinations"]

    combinations_string = ""
    for i, com in enumerate(manpage_data["combinations"]):
        combinations_string += f'{i+1}. "' + '", "'.join(com) + '"\n    '

    prompt_template = Template("""
Here is the document of "$name",

```json
$data
```

Buffer vulnerabilities have occurred in the following option combinations,

$combinations

# Instruction

Please adhere to the following steps to analyze why these option combinations are susceptible to buffer vulnerabilities.

## Steps

1. Understand the core functionality of the program from the "name" and "description" fields.
2. Analyze all the listed options in the "options" field and their respective roles. Disregard options that typically are not combined with others.
3. Remember the constraints  in "requirements" field and use them to guide subsequent steps.
4. Hypothetically analyze why these option combinations are susceptible to buffer vulnerabilities and summarize what kind of combinations of any options that, when used together, could lead to deep memory corruption vulnerabilities while functioning correctly.
5. Examine whether any options in the combination, while not directly causing the vulnerability, might facilitate its trigger.
6. Provide the final results in JSON foramt with no comments, strictly adhering to JSON format standards. Here is an example:
```json
{
    "vulnerability1": "description of type1",
    "vulnerability2": "description of type2"
}
```
    """)
    
    prompt = Template.substitute(prompt_template, name=manpage_data["name"], data=json.dumps(new_manpage_data), combinations=combinations_string)

    responses = gpt_utils.queryOpenAI(prompt, model=model, temperature=0.7, n=choice_number)
    return responses[0]

if __name__ == "__main__":
    
    few_shot_template = Template("""
Instructions:
1. Understand the core functionality of the program from the "name" and "description" fields.
2. Analyze individual options and their respective roles from the "options" field. Disregard options that typically are not combined with others.
3. Enumerate the constraints specified in the 'requirements' field, as these will inform and guide the forthcoming steps.
4. Strategically explore and analyze all possible combinations of options. The focus here is to identify combinations that might lead to deep memory corruption vulnerabilities. These combinations should still function correctly within their intended purpose, meaning they must not violate any constraints outlined in step 3.
5. Look for extra options that might help trigger a vulnerability, even if they don not directly cause it, and add them to the combination. It's important to make sure that adding these options doesn't break the rules set in step 3.
6. Provide the final results in JSON foramt with no comments, strictly adhering to JSON format standards. Here is an example:
```json
{
    "potential vulnerable combinations": [
        ["option_1", "option_2", "option_3"],...
    ]
}
```
                                    
Let's take a deep breath and think step by step. Please show your thoughts in each step.

$fsdata

# Your turn
        
    """
    )
    few_shot_data = ""
    programs = ["htmldoc", "jbig2", "jhead", "makeswf", "mp4box", "opj_compress", "pdf2swf", "yasm"]
    for i in range(len(programs)):
        print(f"[*] Processing {programs[i]} ...")
        manpage_path = os.path.join(prompt_path, f"few-shot/manpage_{programs[i]}.json")
        with open(manpage_path, "r") as f:
            manpage_data = json.loads(f.read())

        new_combinations_value = manpage_data['combinations']
        
        new_com_data = {"potential vulnerable combinations": new_combinations_value}
        updated_com_string = json.dumps(new_com_data, indent=4)
        response = generatePrompt(manpage_data, model, choice_number)
        # print(response)
        
        start_idx = response.find("Step 4")
        end_idx = response.find("Step 5")
        start_of_next_line_after_step_4 = response.find('\n', start_idx) + 1
        start_of_step_5_line = response.rfind('\n', 0, end_idx) + 1
        new_text = response[:start_of_next_line_after_step_4] + response[start_of_step_5_line:]
        
        # Find the last occurrence of ```json to correctly identify the start of the JSON data
        json_str_start = response.rfind("```json")
        json_str_end = response.find("```", json_str_start + 7)
        json_data = json.loads(response[json_str_start + 7:json_str_end].strip())
        vulnerabilities = "\n\n".join(json_data.values())
        few_shot_txt = response[:start_of_next_line_after_step_4] + vulnerabilities + "\n\n" + new_text[start_of_next_line_after_step_4:]

        newjson_str_start = few_shot_txt.rfind("```json")
        final_fs_text = few_shot_txt[:newjson_str_start] + "```json\n" + updated_com_string + "\n```\n\n" 
        input_manpage_data = {"name":manpage_data["name"],"description":manpage_data["description"],"options":manpage_data["options"],"requirements":manpage_data["requirements"]}
        final_fs_text = f"# Example {i+1}\n\n## Input\n\n```json\n" + json.dumps(input_manpage_data) + "\n```\n\n## Output\n\n" + final_fs_text

        few_shot_data += final_fs_text
    
    few_shot = Template.substitute(few_shot_template, fsdata=few_shot_data)
    print(few_shot)
    