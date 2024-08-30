import os
import sys
import json
import shutil
import argparse
from utils.execution_util import ExecutionUtil

execution_util = ExecutionUtil()

fuzzing_dir = os.path.abspath(os.path.dirname(__file__))
project_dir = os.path.abspath(os.path.join(fuzzing_dir, ".."))
seed_dir = os.path.join(fuzzing_dir, "input")
output_dir = os.path.join(fuzzing_dir, "seed_tmp")
fuzzer_dir = "/root/fuzzer"

def runCMinCommands(program, config_data):

    dataset=config_data[program]["dataset"]
    package=config_data[program]["package"]

    with open(os.path.join(fuzzing_dir, "argvs", f"argvs_{program}.txt"), "r") as f:
        argvs = f.read().splitlines()[1:]

    for i, argv in enumerate(argvs):
        my_env = {'HOME': os.environ['HOME']}
        if dataset == "carpetfuzz":
            exec_path=f"/root/programs/{package}/build_afl++/bin"
            if os.path.exists(f"/root/programs/{package}/build_afl++/lib"):
                my_env["LD_LIBRARY_PATH"] = f"/root/programs/{package}/build_afl++/lib"
            stub = argv
            if program == "editcap":
                my_env["AFL_IGNORE_PROBLEMS"] = 1
        else:
            if dataset == "power":
                exec_path=f"/root/programs_rq5/{package}/build_orig/target_afl++_{program}"
                if os.path.exists(f"/root/programs_rq5/{package}/build_orig/lib"):
                    my_env["LD_LIBRARY_PATH"] = f"/root/programs_rq5/{package}/build_orig/lib"
            elif dataset == "configfuzz":
                exec_path=f"/root/programs_configfuzz/{package}/build_orig/target_afl++_{program}"
                if os.path.exists(f"/root/programs_configfuzz/{package}/build_orig/lib"):
                    my_env["LD_LIBRARY_PATH"] = f"/root/programs_configfuzz/{package}/build_orig/lib"
            else:
                print(f"[x] Invalid dataset: {dataset}")
                exit(1)
            first_word = argv.split(" ")[0]
            sub_words = argv.split(" ")[1:]
            if first_word.endswith(".afl"):
                stub = argv
            else:
                stub = f"{first_word}.afl {' '.join(sub_words)}"

        cmd = f"{fuzzer_dir}/afl++/afl-cmin -i {seed_dir}/{program} -o {output_dir}/{program}/{i} -- {exec_path}/{stub}"
        stdout, ret_code = execution_util.executeCommand(cmd, timeout=10, env=my_env)

        print(stdout)

def processOutput(target_dir):
    for dir in os.listdir(target_dir):
        if not os.path.isdir(os.path.join(target_dir, dir)):
            continue
        for file in os.listdir(os.path.join(target_dir, dir)):
            if not os.path.exists(os.path.join(target_dir, file)):
                shutil.move(os.path.join(target_dir, dir, file), os.path.join(target_dir, file))
        shutil.rmtree(os.path.join(target_dir, dir))
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='''
        Prophet-experiments - Prophet's experiments.
        %s - Run afl-cmin to minimize the corpus."
    echo "  -p         Target programs to be fuzzed (Required)."
    echo "  -h         Display this help message."
    ''' % sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--program', type=str, help = 'Target programs to be fuzzed (Required).', required=True)

    args = parser.parse_args()

    program = args.program

    with open (os.path.join(fuzzing_dir, "config.json"), "r") as f:
        config_data = json.loads(f.read())

    if program not in config_data:
        print(f"Invalid program: {program}")
        exit(1)

    print(f"[*] Get the commands list for {program} ...")
    
    runCMinCommands(program, config_data)
    processOutput(os.path.join(output_dir, program))
    
    shutil.rmtree(os.path.join(seed_dir, program))
    shutil.move(os.path.join(output_dir, program), os.path.join(seed_dir, program))
    shutil.rmtree(output_dir)
    
    print(f"[OK] All finished, results are saved in {seed_dir}/{program}.")