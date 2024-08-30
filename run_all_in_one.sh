#!/bin/bash

# Check if a program name is given as an argument
if [ $# -eq 0 ]; then
    echo "Usage: $0 program_name"
    exit 1
fi

program="$1"

# Set base directories
manpage_parser_dir="./manpage_parser"
llm_interface_dir="./llm_interface"
fuzzing_handler_dir="./fuzzing_handler"

echo "[WARN] If you are not within our Docker environment, you may need to manually install dependencies and modify the fuzzing_handler/config.json to specify the path to the program under test."

# Execute Python scripts for parsing, processing, and handling the man page
echo "Parsing the man page for $program ..."
python3 $manpage_parser_dir/parser.py --file $manpage_parser_dir/input/${program}.1

echo "[*] Restructuring the man page ..."
python3 $llm_interface_dir/restruct_manpage.py --file $manpage_parser_dir/output/manpage_${program}.json

echo "[*] Extracting constraints ..."
python3 $llm_interface_dir/constraint.py --file $llm_interface_dir/input/manpage_${program}.json

echo "[*] Predicting High-Risk Option Combinations ..."
echo $llm_interface_dir
python3 $llm_interface_dir/predict.py --file $llm_interface_dir/input/manpage_${program}.json

echo "[*] Assembling the commands ..."
python3 $llm_interface_dir/assemble.py --file $llm_interface_dir/input/manpage_${program}.json

echo "[*] Generating files from the code ..."
python3 $fuzzing_handler_dir/generate_file.py

echo "[*] Generating Argvs for fuzzing ..."
python3 $fuzzing_handler_dir/fix_argvs.py

echo "[*] Running corpus minimization ..."
python3 $fuzzing_handler_dir/run_cmin.py --program $program

# echo "[*] All processes completed successfully."
bash $fuzzing_handler_dir/run_fuzzing.sh -p $program -x
