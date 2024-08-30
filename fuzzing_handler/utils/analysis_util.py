import os
import re
import sys
import signal
import shutil
import atexit
import hashlib
from utils.execution_util import ExecutionUtil
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from sysv_ipc import SharedMemory, IPC_PRIVATE, IPC_CREX

MAP_SIZE = 8 * 1024 * 1024
timeout_seconds = 1

execution_util = ExecutionUtil()

class AnalysisUtil:
    def __init__(self):
        #execution_util.registerSignalEvent()
        atexit.register(execution_util.cleanupSubprocesses)
        return

    # Prevent the program to break the original file
    def copySeedFile(self, seed_path):
        tmpfile_path = "/tmp/.showmap-tmpfile-%s" % (hashlib.md5(seed_path.encode("utf-8")).hexdigest())
        try:
            shutil.copyfile(seed_path, tmpfile_path)
        except IOError as e:
            print("[x] Unable to copy the seed file %s: %s" % (seed_path, e))
            return None
        except:
            print("[x] Unexpected error:", sys.exc_info())
            return None
        return tmpfile_path

    def executeStub(self, stub, mode, env={}):
        find_seed_result = re.findall(r'\S+id:\d{6},\S+', stub)
        tmpfile_path = None
        seed_path = None
        if len(find_seed_result) > 0:
            seed_symbol = find_seed_result[0]
            match = re.search(r'/root/VulPredictor/fuzzing_data/output/\S+/id:\d{6},\S+', seed_symbol)
            if match:
                seed_path = match.group(0).strip("'").strip('"')
            else:
                print(f"[x] Cannot find seed path: {stub}")
                return None

            tmpfile_path = self.copySeedFile(seed_path)
            if tmpfile_path == None:
                return None
            stub = stub.replace(seed_symbol, tmpfile_path)
        
        if mode == "asan":
            execution_cmd = stub
            env = os.environ.copy()
        elif mode == "gdb":
            execution_cmd = (f"gdb -batch -ex \"run\" -ex \"set disable-randomization off\" -ex \"bt\" --args {stub}")
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH"].replace("build_asan", "build_orig")
        elif mode == "edge":
            execution_cmd = (f"timeout {timeout_seconds} {stub}")
            env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]

        stdout, ret_code = execution_util.executeCommand(execution_cmd, env=env)

        if tmpfile_path and os.path.exists(tmpfile_path):
            os.remove(tmpfile_path)

        if ret_code in [-signal.SIGSEGV, -signal.SIGABRT]:
            stdout = "Segmentation fault\n" + stdout

        return stdout

    def extractVulnerabilityFeatures(self, content, mode):
        trace_set = set()
        vul_type = None
        i = 0
        while len(trace_set) < 3:
            if f"#{i}" not in content:
                break
            # E.g., #0 0x7ffff75d608c in __interceptor_memchr ../../../../src/libsanitizer/sanitizer_common/sanitizer_common_interceptors.inc:874
            if mode == "asan":
                trace_pattern = re.compile("#%d .*?in.*? (\S+:\d+)" % i, flags=re.DOTALL)
                # E.g., ==12587==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x611000011541 at pc 0x7ffff75d608d bp 0x7fffffffd980 sp 0x7fffffffd128
                type_pattern = re.compile(r"ERROR: AddressSanitizer: (.+?) on address")
                type_result = type_pattern.search(content)
                if type_result:
                    vul_type = type_result.group(1)
                else:
                    type_pattern = re.compile(r"ERROR: AddressSanitizer: (.+?):")
                    type_result = type_pattern.search(content)
                    if type_result:
                        vul_type = type_result.group(1)
            # E.g., #0  0x00000000004cd275 in xmlSchemaInitTypes () at xmlschemastypes.c:606
            elif mode == "gdb":
                trace_pattern = re.compile("#%d .*?at (\S+:\d+)" % i, flags=re.DOTALL)
                vul_type = "segmentation violation"
            trace_result = re.search(trace_pattern, content)
            if trace_result:
                traceinfo = trace_result.group(1)
                if "../sysdeps/" in traceinfo:
                    i += 1
                    continue
                if "/" in traceinfo:
                    traceinfo = os.path.basename(traceinfo)
                if traceinfo.startswith("raise.c") or traceinfo.startswith("abort.c") or traceinfo.startswith("assert.c") or traceinfo.startswith("malloc.c") or traceinfo.startswith("string_fortified.h") or traceinfo.startswith("asan_") or traceinfo.startswith("sanitizer_") or traceinfo.startswith("libc-start.c"):
                    i += 1
                    continue
                # Avoid loop
                if traceinfo in trace_set:
                    i += 1
                    continue
                trace_set.add(traceinfo)
                i += 1
            else:
                if len(trace_set) > 0:
                    print(f"[x] Discontinuous trace in {mode} mode")
                    break
                i += 1
                continue
        return trace_set, vul_type

    def analyzeVulnerabilities(self, stub_list, output_dir, core_list, json_only_flag):

        if not json_only_flag:
            mode = "write"
        else:
            mode = "read"

        os.sched_setaffinity(0, core_list)
        args_list = []
        for stub in stub_list:
            crash_file = [word for word in stub.split(" ") if "id:" in word][0]
            index = int(os.path.basename(crash_file)[3:9])
            args_list.append((stub, index, output_dir, mode))

        if mode == "read":
            # I/O dense
            with ProcessPoolExecutor(max_workers= 2 * len(os.sched_getaffinity(0))) as executor:
                results = executor.map(self.analyzeEachCrashStdout, args_list)
        else:
            # CPU dense
            with ProcessPoolExecutor(max_workers=len(os.sched_getaffinity(0))) as executor:
                results = executor.map(self.analyzeEachCrashStdout, args_list)
        
        trace_dict = {}
        for item in results:
            if item == None:
                continue
            key, crash_file, vul_type = item
    
            if key not in trace_dict:
                trace_dict[key] = {}
            trace_dict[key][crash_file] = vul_type

        return trace_dict

    def analyzeEdges(self, stub_list, output_dir, core_list, json_only_flag):

        if not json_only_flag:
            mode = "write"
        else:
            mode = "read"

        os.sched_setaffinity(0, core_list)
        args_list = []
        for index, stub in enumerate(stub_list):
            args_list.append((stub, index, output_dir, mode))

        if mode == "read":
            # I/O dense
            with ThreadPoolExecutor(max_workers=2 * len(os.sched_getaffinity(0))) as executor:
                results = executor.map(self.analyzeEachSeedEdges, args_list)
        else:
            # CPU dense
            with ProcessPoolExecutor(max_workers=len(os.sched_getaffinity(0))) as executor:
                results = executor.map(self.analyzeEachSeedEdges, args_list)

        edge_dict = {}
        for each_edge_dict in results:
            for edge in each_edge_dict:
                hit_count = each_edge_dict[edge]
                if edge not in edge_dict:
                    edge_dict[edge] = 0
                edge_dict[edge] = edge_dict[edge] + hit_count

        edges = []
        for key in sorted(edge_dict.keys()):
            edges.append(f"{key}:{edge_dict[key]}")

        return edges

    def checkTraceDeviation(self, stub_list):

        trace_dict = {}
 
        for stub in stub_list:

            key = None

            crash_file = [word for word in stub.split(" ") if "id:" in word][0]

            tmp_set = set()
            for _ in range(20):
                stdout = self.executeStub(stub, mode="asan")

                if stdout == None:
                    print("[x] Empty output detected: {stub}")
                    continue
                trace_set, vul_type = self.extractVulnerabilityFeatures(stdout, mode="asan")
                tmp_set.add(', '.join(sorted(list(trace_set))))
            if "LeakSanitizer" in stdout:
                continue

            if len(trace_set) == 0:
                # Retry with gdb
                if "Segmentation fault" in stdout or "AddressSanitizer" in stdout:
                    gdb_stub = stub.replace("build_asan", "build_orig")

                    gdb_stdout = self.executeStub(gdb_stub, mode="gdb")

                    if gdb_stdout == None:
                        print(f"[x] Empty output detected: {gdb_stub}")
                        key = "unknown"
                        vul_type = "null"
                    else:
                        for _ in range(20):
                            gdb_stdout = self.executeStub(gdb_stub, mode="gdb")

                            if gdb_stdout == None:
                                print(f"[x] Empty output detected: {gdb_stub}")
                                exit(1)

                            gdb_trace_set, gdb_vul_type = self.extractVulnerabilityFeatures(gdb_stdout, mode="gdb")
                            tmp_set.add(', '.join(sorted(list(trace_set))))

                        if len(gdb_trace_set) == 0:
                            print(f"[x] Fail to parse line number in gdb mode: {gdb_stub}")
                            key = "unknown"
                            vul_type = "null"
                # Just a FP
                else:
                    continue

            
            if key == None:
                key = ""
                for trace in tmp_set:
                    key += f"{trace}; "
                key = key[:-1]
            if key not in trace_dict:
                trace_dict[key] = {}
            trace_dict[key][crash_file] = vul_type

        return trace_dict

    def calibrateMapSize(self, stub):
        global MAP_SIZE
        my_env = {
            "AFL_DEBUG": "1"
        }
 
        stdout, _ = execution_util.executeCommand(stub, env=my_env)

        if stdout:
            find_map_result = re.search(re.compile("__afl_final_loc (\d+)"), stdout)
            if find_map_result:
                MAP_SIZE = int(find_map_result.group(1))
        return
    
    def analyzeEachCrashStdout(self, args):
        output_content = ""

        gdb_stub, index, output_dir, mode = args

        asan_stub = gdb_stub.replace("build_orig", "build_asan")

        crash_file = [word for word in gdb_stub.split(" ") if "id:" in word][0]

        if mode == "write":

            gdb_stdout = self.executeStub(gdb_stub, mode="gdb")
            
            output_content += "[*] gdb content\n"
            output_content += gdb_stdout + "\n"
            
            # Try ASAN
            asan_stdout = self.executeStub(asan_stub, mode="asan")

            # A unusual loop casued by DEADLYSIGNAL
            if asan_stdout.count("AddressSanitizer:DEADLYSIGNAL") > 3:
                # We will retry 3 times
                for _ in range(3):
                    asan_stdout = self.executeStub(asan_stub, mode="asan")
                    if asan_stdout.count("AddressSanitizer:DEADLYSIGNAL") <= 3:
                        break
            
            output_content += "[*] asan content\n"
            output_content += asan_stdout + "\n"

            with open("%s/%06d" % (output_dir, index), "w") as f:
                f.write(output_content) 
        elif mode == "read":

            index = int(os.path.basename(crash_file)[3:9])

            if not os.path.exists(os.path.join("%s/%06d" % (output_dir, index))):
                return None
            
            with open(os.path.join("%s/%06d" % (output_dir, index)), "r") as f:
                lines = f.read().splitlines()
            
            mode_data = {
                "gdb": [],
                "asan": []
            }

            current_mode = None
            for line in lines:
                if '[*] gdb content' in line:
                    current_mode = 'gdb'
                elif '[*] asan content' in line:
                    current_mode = 'asan'
                elif current_mode:
                    mode_data[current_mode].append(line)
            
            gdb_stdout = "\n".join(mode_data["gdb"])
            asan_stdout = "\n".join(mode_data["asan"])


        key = None
        if gdb_stdout == "":
            print(f"[x] Empty output detected: {gdb_stub}")
            return None
        
        gdb_trace_set, gdb_vul_type = self.extractVulnerabilityFeatures(gdb_stdout, mode="gdb")
        if len(gdb_trace_set) == 0:
            print(f"[x] Fail to parse line number in gdb mode: {gdb_stub}")

        if asan_stdout == "" or "LeakSanitizer" in asan_stdout:
            # Just a FP
            if len(gdb_trace_set) == 0:
                return None
            print(f"[x] Empty output detected: {asan_stub}")
            trace_set = gdb_trace_set
            vul_type = gdb_vul_type
        else:
            # A unusual loop casued by DEADLYSIGNAL
            if asan_stdout.count("AddressSanitizer:DEADLYSIGNAL") > 3 and len(gdb_trace_set) == 0:
                key = "deadlysignal"
                vul_type = "null"
            else:
                asan_trace_set, asan_vul_type = self.extractVulnerabilityFeatures(asan_stdout, mode="asan")
                if len(asan_trace_set) == 0:
                    # Just a FP
                    if len(gdb_trace_set) == 0:
                        return None
                    trace_set = gdb_trace_set
                    vul_type = gdb_vul_type
                else:
                    trace_set = asan_trace_set if len(gdb_trace_set) == 0 else gdb_trace_set
                    vul_type = asan_vul_type

        if key == None:
            key = ', '.join(sorted(list(trace_set)))

        return (key, crash_file, vul_type)

    
    def analyzeEachSeedEdges(self, args):
        stub, index, output_dir, mode = args

        if mode == "write":
            shm = SharedMemory(IPC_PRIVATE, flags=IPC_CREX, mode=0o600, size=MAP_SIZE, init_character=b'\x00')

            my_env = {
                '__AFL_SHM_ID': str(shm.id),
                'AFL_MAP_SIZE': str(MAP_SIZE),
                'LD_LIBRARY_PATH': os.environ["LD_LIBRARY_PATH"],
                'HOME': os.environ['HOME']
            }

            if "AFL_IGNORE_PROBLEMS" in os.environ:
                my_env["AFL_IGNORE_PROBLEMS"] = "1"

            shm_content = shm.read()

            assert shm_content == bytes([0] * MAP_SIZE)

            self.executeStub(stub, mode="edge", env=my_env)

            shm_content = shm.read()

            shm.detach()
            shm.remove()

            edges = []
            if shm_content[0] == 0:
                print("[x] No coverage detected!")
            else:
                for i in range(1, MAP_SIZE):
                    if shm_content[i] == 0:
                        continue
                    edges.append("%06d:%d" % (i, int(shm_content[i])))

            with open("%s/%06d" % (output_dir, index), "w") as f:
                f.write("\n".join(edges))  
            lines = edges
        else:
            with open("%s/%06d" % (output_dir, index), "r") as f:
                lines = f.read().splitlines()
            
        edge_dict = {}

        for line in lines:
            edge = line.split(":")[0]
            hit_count = int(line.split(":")[1])
            if edge not in edge_dict:
                edge_dict[edge] = 0
            edge_dict[edge] = edge_dict[edge] + hit_count
        
        return edge_dict