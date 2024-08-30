#!/bin/bash

repo_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../" &> /dev/null && pwd )"
fuzzing_dir="${repo_dir}/fuzzing_handler"
output_dir="${fuzzing_dir}/output"
fuzzer_dir="${repo_dir}/fuzzer"

config_file=$(cat "${fuzzing_dir}/config.json")

usage() {
    echo "ProphetFuzz-experiments - ProphetFuzz's experiments."
    echo "run_fuzzing.sh - Run all fuzzing instances in the paper."
    echo
    echo "Usage: $0 [-c CORES] [-r REPETITIONS] [-e] [-s] [-p PROGRAM] [-h]"
    echo
    echo "Options:"
    echo "  -c CORES   Number of cores to be used (default: number of available CPU cores)."
    echo "  -r REPEAT  Number of repetitions (default: 5)."
    echo "  -d DAY     Number of days (default: 3)."
    echo "  -p         Target programs to be fuzzed, splitted by comma (Required)."
    echo "  -f CORE_ID  First core id to be used (default: 0)."
    echo "  -x         Persistent mode."
    echo "  -h         Display this help message."
}

runFuzzing() {
    total_runs=$1
    cores=$2

    # Prepare fuzzing environment
    echo core >/proc/sys/kernel/core_pattern
    cd /sys/devices/system/cpu
    echo performance | tee cpu*/cpufreq/scaling_governor

    printf '%s\n' "${total_runs[@]}"| xargs -P ${cores} -n 1 -I {} bash -c "{}"
}

prepareFuzzingCommands() {
    cores=$1
    core_id=$2
    repeat=$3
    programs=$4
    days=$5
    persistent_flag=$6

    total_runs=()

    cpu_bind=${core_id}

    fuzzer="prophetfuzz"

    # Persistent Fuzzing
    if [[ $persistent_flag == true ]]; then
        timeout_slice=""
    else    
        timeout_slice="timeout ${days}d"
    fi

    IFS=',' read -r -a array <<< "$programs"

    for program in "${array[@]}"; do
        if ! $(echo "$config_file" | jq -e --arg prog "$program" 'has($prog)'); then
            echo "Invalid program: ${program}"
            exit 1
        fi
    done

    for program in "${array[@]}"; do
        dataset=$(echo "$config_file"|jq --arg prog "$program" '.[$prog].dataset'|tr -d '"')
        package=$(echo "$config_file"|jq --arg prog "$program" '.[$prog].package'|tr -d '"')
        stub=$(echo "$config_file"|jq --arg prog "$program" '.[$prog].stub'|tr -d '"')

        for index in $(seq 1 "${repeat}"); do
            
            task="${program}_${fuzzer}_${index}"

            input_path="${fuzzing_dir}/input/${program}"

            output_path="${output_dir}/${task}"

            if [[ "$dataset" == "carpetfuzz" ]]; then
                exec_path="/root/programs/${package}/build_${fuzzer}/bin"
                cmd="AFL_IGNORE_SEED_PROBLEMS=1 LD_LIBRARY_PATH=/root/programs/${package}/build_${fuzzer}/lib"
                if [[ $program == "editcap" ]]; then
                    cmd="AFL_IGNORE_PROBLEMS=1 $cmd"
                fi
            elif [[ "$dataset" == "power" ]];then
                exec_path="/root/programs_rq5/${package}/build_orig/target_${fuzzer}_${program}"
                cmd="AFL_IGNORE_SEED_PROBLEMS=1 LD_LIBRARY_PATH=/root/programs_rq5/${package}/build_orig/lib"
                stub=$(echo "$stub" | awk '{print ($1 ~ /\.afl$/) ? $0 : $1 ".afl " substr($0, length($1) + 2)}')
            elif [[ "$dataset" == "configfuzz" ]];then
                exec_path="/root/programs_configfuzz/${package}/build_orig/target_${fuzzer}_${program}"
                cmd="AFL_IGNORE_SEED_PROBLEMS=1 LD_LIBRARY_PATH=/root/programs_configfuzz/${package}/build_orig/lib"
                stub=$(echo "$stub" | awk '{print ($1 ~ /\.afl$/) ? $0 : $1 ".afl " substr($0, length($1) + 2)}')
            else
                echo "Invalid dataset: $dataset"
                exit 1
            fi

            argvs_path="${fuzzing_dir}/argvs/argvs_${program}.txt"
            
            cmd="$cmd screen -dmS ${task} ${timeout_slice} ${fuzzer_dir}/afl-fuzz -i ${input_path} -o ${output_path} -b ${cpu_bind} -m none -K ${argvs_path} -- ${exec_path}/${stub}"

            total_runs+=("${cmd}")
            cpu_bind=`expr ${cpu_bind} + 1`
        done
    done

    for cmd in "${total_runs[@]}"
    do
        echo -e "$cmd\n"
    done
}

programs=null
persistent_flag=false
while getopts "c:r:p:d:f:xh" opt; do
    case $opt in
        c) cores=$OPTARG ;;
        r) repeat=$OPTARG ;;
        p) programs=$OPTARG ;;
        d) days=$OPTARG ;;
        f) core_id=$OPTARG ;;
        x) persistent_flag=true ;;
        h)
            usage
            exit 0
            ;;
        \?)
            echo "Invalid option: -$OPTARG"
            usage
            exit 1
            ;;
    esac
done

cores=${cores:-$(nproc)}
repeat=${repeat:-5}
days=${days:-3}
core_id=${core_id:-0}

if [[ "$programs" == null ]]; then
    usage
    exit 1
fi

if (( cores > $(nproc) )); then
    echo "[x] Not enough cores!"
    exit 1
fi

echo "[*] Number of cores to be used: ${cores}, start at ${core_id}, repeat ${repeat} times, last for ${days} days"

echo "[*] Get the commands list for ${programs} ..."
IFS=$'\n' read -rd '' -a total_runs <<< "$(prepareFuzzingCommands ${cores} ${core_id} ${repeat} ${programs} ${days} ${persistent_flag})"

# printf "%s\n" "${total_runs[@]}"
# exit 1
echo "[*] Start Fuzzing ..."
runFuzzing "${total_runs}" "${cores}"

echo "[OK] All finished, results are saved in ${fuzzing_dir}/output/."